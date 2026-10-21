# Context

## Purpose

Make the account-health and replay answer independent of whether upstream chose to send an error code.

## Upstream provenance

Narrow port of upstream #2449 (`143e07d06`): message-derived usage-limit classification. Skipped: upstream's
Retry-After stamping for the message-derived 429, which depends on its burst-429 machinery.

## Decisions

- Only `upstream_error` (the normalization of a missing code) may be reclassified by message; `invalid_request_error`
  is deliberately excluded because it can echo request content.
- Plain `rate_limit_exceeded` throttling is not a usage-limit exhaustion.

## Failure modes

- Upstream rewording the sentence falls back to the old transient behavior; the marker list lives in `app/core/errors.py`.

## Example

Frame `{"type":"response.failed","response":{"error":{"message":"The usage limit has been reached"}}}`: account A is
benched, request completes on B.
