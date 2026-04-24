## MODIFIED Requirements

### Requirement: Strip downstream transport headers before upstream forwarding
Before forwarding Responses or compact requests upstream, the service MUST strip downstream hop-by-hop, proxy-loop, and body-framing headers that are owned by the client-to-proxy connection. The service MUST remove `Connection`, headers named by `Connection`, `Transfer-Encoding`, `TE`, `Trailer`, `Upgrade`, `Keep-Alive`, `Proxy-Authorization`, `Proxy-Authenticate`, `Proxy-Connection`, `Content-Length`, `Content-Encoding`, `Content-Type`, `Accept`, `Accept-Encoding`, `Host`, `Cookie`, `CDN-Loop`, `Forwarded`, `X-Forwarded-*`, `X-Real-IP`, `True-Client-IP`, and `CF-*` before building the upstream request. The service MUST set upstream auth, account, `Accept`, and `Content-Type` headers from internal proxy state.

#### Scenario: Compact request arrives chunked
- **WHEN** a client sends `/backend-api/codex/responses/compact` or `/v1/responses/compact` with `Transfer-Encoding: chunked`
- **THEN** the upstream compact request does not include `Transfer-Encoding`
- **AND** the proxy-generated upstream JSON request remains eligible for the direct compact contract

#### Scenario: Connection-nominated extension header is present
- **WHEN** a downstream request includes `Connection: keep-alive, X-Remove-Me` and `X-Remove-Me`
- **THEN** neither `Connection` nor `X-Remove-Me` is forwarded upstream
