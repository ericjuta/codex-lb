# Tasks

## 1. Release the routed response

- [x] 1.1 Coordinate duck-typed `release_codex_response` with LoggingPorts.
- [x] 1.2 Release the raw response in the routed HTTP stream `finally`.
- [x] 1.3 Forward `release()` from `_CodexSSEResponse`.

## 2. Deterministic generator teardown

- [x] 2.1 Consume `_iter_sse_events` under `contextlib.aclosing` on both HTTP sites.
- [x] 2.2 Propagate `aclosing` through `stream_responses` and the HTTP attempt chain.
- [x] 2.3 Aclose each continuation round's `_stream_responses_with_session`.

## 3. Verification

- [ ] 3.1 Unit release-order cases (parent).
- [ ] 3.2 Integration aiohttp unclosed-connection cases (parent).
