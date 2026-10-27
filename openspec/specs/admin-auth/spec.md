# admin-auth Specification

## Purpose

Define dashboard authentication behavior so login, bootstrap, TOTP, and session handling stay secure and predictable.
## Requirements
### Requirement: Login rate limiting

The system SHALL rate-limit failed password login attempts using the existing `TotpRateLimiter` pattern: maximum 8 failures per 60-second window. On rate limit breach, the system MUST return 429 with a `Retry-After` header. Requests rejected because password login is not configured MUST NOT consume that failed-login budget.

#### Scenario: Rate limit triggered

- **WHEN** 8 failed login attempts occur within 60 seconds
- **THEN** the 9th attempt returns 429 with `Retry-After` header indicating seconds until the window resets

#### Scenario: Rate limit resets on success

- **WHEN** a successful login occurs after failed attempts
- **THEN** the failure counter for that client resets to zero

#### Scenario: Unconfigured password login does not spend rate-limit budget

- **WHEN** no password is configured and a login request is submitted
- **THEN** the system returns `password_not_configured`
- **AND** it does not consume one of the failed-login attempts for that client

### Requirement: Password length is bounded by bcrypt's input limit

The system SHALL enforce minimum and maximum dashboard password lengths for `POST /api/dashboard-auth/password/setup` and `POST /api/dashboard-auth/password/change`'s `new_password`. The maximum MUST be exactly 72 UTF-8 bytes, matching bcrypt's limit, not 72 codepoints.

#### Scenario: Setup rejects passwords longer than 72 bytes

- **WHEN** `POST /api/dashboard-auth/password/setup` receives a password whose UTF-8 encoded length exceeds 72 bytes
- **THEN** the system returns HTTP 422 with error code `password_too_long`
- **AND** the response message references the 72-byte limit so the client can render it

#### Scenario: Setup accepts passwords up to 72 bytes inclusive

- **WHEN** `POST /api/dashboard-auth/password/setup` receives a password whose UTF-8 encoded length is exactly 72 bytes
- **THEN** the system accepts the password and configures it

#### Scenario: Length is measured in UTF-8 bytes, not codepoints

- **WHEN** `POST /api/dashboard-auth/password/setup` receives a password whose codepoint count is below 72 but whose UTF-8 encoded length exceeds 72 bytes (e.g. an emoji-only string)
- **THEN** the system returns HTTP 422 with error code `password_too_long`

#### Scenario: Change applies the same upper bound to the new password

- **WHEN** `POST /api/dashboard-auth/password/change` receives a `new_password` whose UTF-8 encoded length exceeds 72 bytes
- **THEN** the system returns HTTP 422 with error code `password_too_long` before attempting to hash the password

### Requirement: Dashboard password sessions use a configurable absolute lifetime

Persisted dashboard settings SHALL control dashboard password-authenticated sessions' absolute lifetime, defaulting to 12 hours. Newly issued sessions SHALL set both the encrypted expiry payload and cookie `Max-Age` to that lifetime.

#### Scenario: Newly issued dashboard password session honors configured lifetime

- **WHEN** an admin configures a dashboard session lifetime and successfully completes password authentication
- **THEN** the newly issued dashboard session expires after the configured absolute lifetime
- **AND** the cookie `Max-Age` matches the same configured lifetime

#### Scenario: Existing dashboard sessions keep their original expiry

- **WHEN** an admin changes the configured dashboard session lifetime after a session cookie has already been issued
- **THEN** previously issued cookies continue to expire according to the expiry embedded in their encrypted payload
- **AND** only newly issued dashboard password sessions use the updated lifetime

### Requirement: Trusted proxy client identity resists appended Forwarded chain spoofing

With proxy-header trust enabled and the socket peer in a configured trusted proxy CIDR, the system MUST resolve RFC 7239 `Forwarded` right-to-left. It MUST advance to an earlier `for=` hop only while the immediately downstream peer is trusted.

#### Scenario: Client-preseeded loopback value cannot bypass remote bootstrap protection

- **WHEN** a trusted socket proxy appends `for=203.0.113.24` to a client-supplied `Forwarded: for=127.0.0.1` value
- **THEN** the resolved client is `203.0.113.24`
- **AND** the request is not classified as local

#### Scenario: Proxy appends a separate Forwarded field

- **WHEN** a client supplies `Forwarded: for=127.0.0.1`
- **AND** a trusted socket proxy appends a second `Forwarded: for=203.0.113.24` field
- **THEN** the system combines both field values in arrival order
- **AND** resolves the client as `203.0.113.24`
- **AND** does not classify the request as local

#### Scenario: Complete trusted multi-proxy chain resolves the originating client

- **WHEN** the socket peer and each downstream proxy hop belong to configured trusted proxy CIDRs
- **AND** the `Forwarded` elements contain one valid IP `for=` node per hop
- **THEN** the system resolves the originating client IP from the earliest reachable element

### Requirement: Forwarded elements require valid RFC 7239 syntax

For trusted-proxy resolution, each `Forwarded` element MUST have exactly one valid IP `for=` node, optionally with a valid port. Names/values MUST use RFC 7239 token or quoted-string syntax. Names MUST NOT repeat per element. IPv6 nodes MUST be bracketed and quoted. Port-bearing nodes MUST be quoted. Numeric ports MUST have 1–5 ASCII digits within `0..65535`. Otherwise the entire `Forwarded` value MUST fail closed and MUST NOT classify the request as local.

#### Scenario: Malformed or incomplete Forwarded chain fails closed

- **WHEN** any `Forwarded` element has a missing, duplicate, obfuscated, unknown, or malformed `for=` node
- **THEN** trusted proxy client resolution returns no client IP from that header
- **AND** the request is not classified as local

#### Scenario: Unquoted IPv6 or port-bearing node fails closed

- **WHEN** a `Forwarded` element contains an unquoted bracketed IPv6 node or an unquoted node with a port
- **THEN** trusted proxy client resolution returns no client IP from that header
- **AND** the request is not classified as local

#### Scenario: Bracketed IPv6 node with port is resolved

- **WHEN** a trusted socket proxy supplies a valid quoted bracketed IPv6 `for=` node with a numeric port
- **THEN** the system resolves the IPv6 address without the brackets or port

### Requirement: Singleton client-IP headers reject repeated fields

`X-Real-IP`, `True-Client-IP`, and `CF-Connecting-IP` MUST each occur at most once. Repetition MUST yield no resolved client IP and MUST NOT establish locality.

#### Scenario: Repeated singleton client-IP header fails closed

- **WHEN** a trusted socket request contains more than one field for `X-Real-IP`, `True-Client-IP`, or `CF-Connecting-IP`
- **THEN** trusted proxy client resolution returns no client IP
- **AND** the request is not classified as local

### Requirement: Trusted-proxy locality requires trusted socket provenance

With proxy-header trust enabled, the system MUST classify a forwarded loopback client as local only if its raw socket peer matches a configured trusted-proxy CIDR and forwarded resolution succeeds. A forwarded client-IP header from an untrusted socket peer MUST NOT establish locality or bypass remote dashboard bootstrap requirements.

#### Scenario: Untrusted loopback proxy cannot bypass remote bootstrap

- **WHEN** proxy-header trust is enabled
- **AND** the raw loopback socket peer is outside every configured trusted-proxy CIDR
- **AND** the request supplies a local Host header and a forwarded client-IP header
- **THEN** the request is classified as remote
- **AND** first-run password setup requires the configured bootstrap token

#### Scenario: Trusted proxy may forward a loopback client

- **WHEN** proxy-header trust is enabled
- **AND** the raw socket peer belongs to a configured trusted-proxy CIDR
- **AND** valid forwarded client resolution yields a loopback address
- **AND** the Host header is local
- **THEN** the request is classified as local

### Requirement: Direct locality inspects every forwarded client hint field

When proxy-header trust is disabled, the system MUST classify a loopback socket peer with a local Host as local only when no non-empty forwarded client-IP field value is present. When such a header occurs more than once, the system MUST inspect every field value rather than only the first.

#### Scenario: Later duplicate forwarded hint prevents local bootstrap

- **WHEN** proxy-header trust is disabled
- **AND** a loopback request with a local Host contains an empty `X-Forwarded-For` field followed by a non-empty `X-Forwarded-For` field
- **THEN** the request is classified as remote
- **AND** first-run password setup requires the configured bootstrap token

### Requirement: Security audit reads require an admin principal

The dashboard security-audit route MUST require an admin principal. A guest MUST receive HTTP 403 with `admin_access_required` and MUST NOT receive an audit row, actor IP, identifying detail, or request ID. An admin MUST retain the existing response contract including `actorIp`, `details`, and `requestId`.

#### Scenario: Guest cannot read security-audit records

- **GIVEN** an audit row contains identifying fields
- **WHEN** a guest requests `GET /api/audit-logs`
- **THEN** the response is HTTP 403 `admin_access_required`
- **AND** no identifying audit value is returned

#### Scenario: Admin retains security-audit detail

- **WHEN** an admin requests the same row
- **THEN** the request succeeds
- **AND** actor IP, details, and request ID remain present
