# Tasks

## 1. Implementation

- [x] 1.1 Add model-scoped transient health to the load balancer runtime state and the selection filter.
- [x] 1.2 Pass the served model from the stream, websocket, HTTP bridge and compact health-write call sites.
- [x] 1.3 Name the model in the two health log lines.

## 2. Tests

- [x] 2.1 Selection: model gates, backoff fallback, cooldown hint (`tests/unit/test_load_balancer.py`).
- [x] 2.2 Load balancer: record, cooldown, success clearing, expiry, soft-drain overlay, entry bound, single-account selection (`tests/unit/test_load_balancer_model_health.py`).
- [x] 2.3 Stream path regression: three handshake `403`s for one model leave another model served (`tests/integration/test_proxy_transient_retry.py`). It fails on the parent commit at the "other model served" assertion.
- [x] 2.4 Update call-contract assertions and fakes that now carry the model.

## 3. Validation

- [x] 3.1 Pytest for the balancer, load balancer, stream, websocket, bridge and compact suites.
- [x] 3.2 Ruff lint and format, `ty` on `app`.
- [x] 3.3 Strict-validate this OpenSpec change.
