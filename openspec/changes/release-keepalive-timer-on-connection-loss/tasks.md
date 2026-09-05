## 1. Implementation

- [x] 1.1 Add timer-only `KeepAliveHttpToolsProtocol.connection_lost` override.
- [x] 1.2 Add the identical override to `KeepAliveH11Protocol`.
- [x] 1.3 Add `load_http_protocol_class(http)` preserving auto/h11/httptools.
- [x] 1.4 Coordinate CLI 300 s default/help and `http=` wiring with LoggingPorts.

## 2. Validation

- [x] 2.1 Fake-transport regressions over both subclasses.
- [x] 2.2 Live-server RST socket regression.
- [x] 2.3 Stock uvicorn canaries demonstrate retained timers after error close.
- [x] 2.4 Real-socket auto/h11/httptools selection, auto fallback without httptools, and explicit missing-dependency failure.
