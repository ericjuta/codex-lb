# Context: omit unsupported probe token limit

## Purpose and scope

Dashboard Force Probe (`POST /api/accounts/{account_id}/probe`) sends one fixed `responses.create` request, pinned to one account, straight through the shared aiohttp client in `AccountsService._send_probe_request`. This change removes `max_output_tokens` from that request body and deletes the `PROBE_MAX_OUTPUT_TOKENS` constant. It is a narrow port of upstream `f8ffbac20` (#2496).

In scope: the probe request body, the constant, and regression coverage at the route. Everything else about the probe stays the same: model choice, the one-dot instructions and input, `stream=true`, `store=false`, bearer and `chatgpt-account-id` headers, the 30s total / 10s connect timeouts, returning once response headers arrive without reading the SSE stream, passing the upstream status through as `probe_status_code` (`0` on network failure), the forced usage refresh, the audit entry, and dashboard auth and `404`/`409` handling.

## Decision and evidence boundary

- The field is removed outright, with no replacement cap, setting, retry, or sanitizer. Normal Responses forwarding already strips it (`_UNSUPPORTED_UPSTREAM_FIELDS` in `app/core/openai/requests.py`); the fixed probe body was the only path still sending it.
- Upstream evidence: #2496 reports that Codex returned HTTP 400 `Unsupported parameter: max_output_tokens` for a probe body with `max_output_tokens=16`, and HTTP 200 for the same body without the field. This fork has not reproduced that against live upstream, and this change makes no claim to have done so.
- Local evidence is limited to a loopback aiohttp stub that mimics the rejection: it returns 400 when the field is present and 200 otherwise. The route regression proves the fork no longer sends the field and that the accepted status reaches the operator. It does not prove current live upstream behaviour.

## Supersession history

Two earlier `usage-refresh-policy` changes defined an output-token value for the probe body:

- `add-account-probe-endpoint`: its scenario sent `max_output_tokens=1`.
- `probe-valid-token-floor`: it raised the value to `16` (after #1895 showed `1 → 400`, `16 → 200`) and forbade values below that floor.

This change replaces only their output-token clauses. Their endpoint, eligibility, snapshot, and dashboard contracts still apply. Neither output-token clause may be carried into the canonical spec. When this change is synced, the `16`-floor explanation in canonical `usage-refresh-policy/context.md` must be replaced with this omission rationale. Marking those change artifacts as historical is handled outside this change.

## Constraints and non-goals

- Upstream-only probe settlement helpers (`record_account_probe_result`, `get_proxy_service_for_app`, `force_refresh_result`) and probing-health recovery streaks are not ported.
- Limit warmup's `max_output_tokens=4` is untouched. It goes through `ResponsesRequest`, which already strips the field.
- No configuration, schema, data, migration, routing, or dependency changes.
- Account identity, auth refresh, pinning, and usage-settlement behaviour are unchanged.

## Failure modes

- **Field reintroduced**: an upstream that rejects it returns 400, the probe reports `probeStatusCode: 400` for a usable account, and the limiter is not woken. The route regression catches this.
- **Upstream rejects something else**: the status is still passed through unchanged. There is no retry, so the single request's status stays visible to the operator.
- **Network failure or timeout**: `probe_status_code` is `0` within the existing timeout bounds, and the access token is not logged.
- **No output cap**: the one-dot prompt and header-only return keep upstream work small, but a probe may still spend some quota, as before.

## Example

Probe request body after this change (account and model illustrative):

```json
{
  "model": "gpt-5.5",
  "instructions": "Respond with a single dot.",
  "input": [{"role": "user", "content": [{"type": "input_text", "text": "."}]}],
  "stream": true,
  "store": false
}
```

Against a stub that returns 400 whenever `max_output_tokens` is present, `POST /api/accounts/{id}/probe` responds `200` with `"probeStatusCode": 200`. Before this change, the same stub produced `"probeStatusCode": 400`.
