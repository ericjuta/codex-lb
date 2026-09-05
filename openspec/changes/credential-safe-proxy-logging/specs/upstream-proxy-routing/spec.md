## ADDED Requirements

### Requirement: Routed aiohttp egress carries proxy credentials outside the proxy URL

When the Codex upstream client dispatches a routed HTTP request or WebSocket
connect through aiohttp, it MUST pass a credential-free proxy URL
(`scheme://host:port`) and MUST carry the endpoint username and password as a
`Proxy-Authorization` Basic header whose bytes are identical to the header
aiohttp derives from URL userinfo (latin1 encoding). The client MUST NOT place
proxy credentials in the aiohttp proxy URL. Because aiohttp forwards proxy
headers only on the CONNECT tunnel, a route whose ordered pool contains any
credentialed endpoint MUST fail closed for a non-TLS (`http`/`ws`) upstream
target before any connection is opened and ahead of every transport branch
(aiohttp and SOCKS), surfacing as a credential-free connect-phase
transport error, so a credential-free fallback endpoint cannot absorb the
misconfigured primary. Route resolution MUST fail closed for an `http` or
`https` proxy username containing `:`. SOCKS5/SOCKS5H RFC 1929 usernames MAY
contain `:`. SOCKS transports keep carrying credentials through their
existing field inputs. HTTP/SOCKS endpoints MAY still store credentials;
aiohttp dispatch MUST still pass a credential-free proxy URL.

#### Scenario: Credentialed https endpoint uses Proxy-Authorization

- **GIVEN** a resolved `https` proxy endpoint with a username and password
- **WHEN** the Codex upstream client sends a routed request or opens a routed WebSocket through aiohttp
- **THEN** the aiohttp `proxy` argument contains no userinfo
- **AND** the CONNECT request carries a `Proxy-Authorization` header whose value is byte-identical to the userinfo-derived token
- **AND** the aiohttp connection-key repr and the proxy-error message text contain neither the password nor its Basic token
- **AND** the proxy-error repr, which carries the tunnel request headers, renders with `Basic [REDACTED]` through the log formatters (see `proxy-runtime-observability`)

#### Scenario: Credentialed route to a plaintext target fails closed

- **GIVEN** a resolved route whose primary proxy endpoint carries credentials and whose fallback does not
- **WHEN** the Codex upstream client is asked to reach an `http` or `ws` upstream URL, for an idempotent or non-idempotent request or a WebSocket open
- **THEN** the client fails before dispatch with a credential-free connect-phase transport error
- **AND** no endpoint in the pool, including the credential-free fallback, receives the request on any transport

#### Scenario: HTTP username with a colon is rejected at resolution

- **WHEN** an `http` or `https` proxy endpoint username contains `:`
- **THEN** route resolution fails closed with reason `invalid_proxy_username`

#### Scenario: SOCKS username with a colon is accepted at resolution

- **WHEN** a `socks5` or `socks5h` proxy endpoint username contains `:`
- **THEN** route resolution succeeds and preserves the username
