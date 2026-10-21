## Tasks

- [x] Add the usage-limit message predicate and the shared `is_upstream_usage_limit_rejection`.
- [x] Classify the code-less form as `rate_limit` and bench the account.
- [x] Thread the message into stream and WebSocket health/retry/replay decisions.
- [x] Add stream and WebSocket regressions (coded and code-less forms), plus the echoed-sentence negative.
- [x] Route the code-less form through the HTTP-stream previous-response owner rewrite (`_rewrite_previous_response_stream_error`) so owner-pinned streams fail closed and defer owner health like the coded form (review finding; regression in `test_stream_responses_route_keyed_owner_rewrite_settles_before_original_health`).
- [x] Run focused tests, ruff, and strict OpenSpec validation.
