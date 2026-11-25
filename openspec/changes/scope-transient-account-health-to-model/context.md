# Context

## Incident, 2026-11-25 08:08Z

Read from `request_logs` and the container log of the deployed build `5f67f6c17`:

| Model | Result | Count (08:00-09:38Z) |
|---|---|---|
| `gpt-6.1-terra` | success | 276 |
| `gpt-6.1-terra` | 429 `turn_rate_limit_exceeded` | 1,586 |
| `gpt-6.1-terra` | 403 handshake "Invalid response status" | 967 |
| `gpt-6.2-sol` | success | 59 |
| `gpt-6.2-sol` | `no_accounts` | 3 |

- 1,180 "Recorded transient account error ... code=upstream_error" lines and 0 "Applied connect-phase forbidden cooldown" lines: on the HTTP stream path the handshake `403` reaches the generic transient branch, not the connect-phase one.
- 1,042 "No account selected ... model=gpt-6.1-terra" and 88 "... model=gpt-6.2-sol" warnings. The Sol ones are the collateral this change removes.
- The `429` is not penalized; it is logged as "Not retrying non-recoverable stream failure".

## Example

Account P serves Terra and Sol. Three Terra requests on P fail with a handshake `403` and no Terra request succeeds in between.

- Before: P is in backoff for 30 seconds for every model. A Sol request from a key pinned to P gets `no_accounts`.
- After: P is in backoff for 30 seconds for Terra. The Sol request selects P. If Sol also fails three times on P, Sol gets its own backoff.

## Not changed

The client that caused the burst (the OptChat compressor retrying on every appended message) is fixed in its own repository. This change only stops one model's failures from taking the account away from the others.

## Verification (2026-11-25)

- The stream regression test fails on the parent commit `af6c5a22f` at the "other model served" assertion and passes with this change.
- `pytest tests/unit tests/integration -n 8 -k "proxy or balanc or stick or websocket or bridge or compact or select or routing or failover or transient or account"`: 3,627 passed, 11 skipped. One unrelated test (`test_live_usage_ingest.py::test_live_ingestor_writes_usage_rows_for_internal_account`) hung under that loaded run and passes alone (7 passed in its file); this change does not touch its module.
- After the last source edit: balancer, load balancer and transient-retry suites 325 passed; `ruff check`, `ruff format --check` and `ty check app` clean.
- Local runs set `CODEX_LB_PROXY_ACCOUNT_STREAM_LIMIT=8`, because the workstation `.env.local` raises it to 16 and one existing stream-cap test assumes the default.
- Not verified: live behaviour. The change is not deployed by this change set.
