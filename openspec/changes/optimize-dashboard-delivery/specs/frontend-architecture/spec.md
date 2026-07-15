## ADDED Requirements

### Requirement: Dashboard responses use path-safe compression and caching
The service MUST apply gzip compression only to eligible dashboard API responses and SPA assets under `/api/` and `/assets/`. It MUST NOT apply dashboard compression to proxy HTTP streams, websocket routes, or ranged asset responses. Content-hashed SPA assets under `/assets/` MUST be served with a one-year immutable cache policy, while the SPA entry document MUST require revalidation.

#### Scenario: Dashboard API response is compressible
- **WHEN** a client that accepts gzip requests a dashboard API response large enough to compress
- **THEN** the response is gzip encoded

#### Scenario: Proxy stream bypasses dashboard compression
- **WHEN** a client requests a proxy streaming route such as `/backend-api/codex/responses`
- **THEN** the dashboard compression middleware does not encode or buffer the response

#### Scenario: Ranged asset response preserves byte offsets
- **WHEN** a client requests a SPA asset with a `Range` header
- **THEN** the response bypasses gzip compression
- **AND** the returned range describes bytes from the original asset representation

#### Scenario: Hashed asset and entry document use distinct cache policies
- **WHEN** a client requests a content-hashed file under `/assets/`
- **THEN** the response includes `Cache-Control: public, max-age=31536000, immutable`
- **AND** a request for `index.html` receives a `no-cache` policy

### Requirement: Dashboard routes and charting code load on demand
The SPA MUST preserve every configured dashboard route while loading route modules on demand. Recharts runtime code MUST NOT be a static dependency or modulepreload of the initial entry chunk when no chart route has been visited.

#### Scenario: Initial dashboard load excludes unvisited page modules
- **WHEN** the production SPA bundle is built
- **THEN** page modules are emitted behind dynamic route imports
- **AND** the initial entry chunk does not statically import every page module

#### Scenario: Existing deep link remains routable
- **WHEN** a user opens any dashboard route that existed before this change
- **THEN** the corresponding page module loads and renders through the unchanged route path

#### Scenario: Charts remain deferred
- **WHEN** the production SPA bundle is built
- **THEN** the Recharts bundle is not statically imported or modulepreloaded by the initial entry chunk

### Requirement: Dashboard fonts are self-hosted
The dashboard MUST serve JetBrains Mono from bundled application assets, MUST use `font-display: swap`, and MUST NOT require Google Fonts or another third-party font origin during page load.

#### Scenario: Dashboard loads without external font access
- **WHEN** the production SPA is built and loaded in an environment without internet egress
- **THEN** JetBrains Mono is available from local font assets
- **AND** generated dashboard HTML and CSS contain no `fonts.googleapis.com` or `fonts.gstatic.com` reference
