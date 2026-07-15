# Dashboard delivery optimization context

## Purpose and scope

This change ports three reviewed upstream optimizations into the fork while preserving the fork's dashboard pages, routes, translations, and settings. The scope is delivery behavior: response encoding and caching, JavaScript load boundaries, and font hosting. It does not redesign dashboard UI, change proxy request behavior, or introduce deployment configuration.

## Decisions and rationale

- Compression is restricted to bounded `/api/` responses. Static `FileResponse` bodies under `/assets/` stay identity encoded because their streaming gzip framing is not reliably forwarded by every reverse proxy. Proxy endpoints stream SSE or websocket traffic and must also remain outside a buffering compression wrapper.
- Requests carrying `Range` bypass compression because a static-file `206 Content-Range` describes offsets in the original representation.
- Only Vite content-hashed `/assets/` files receive a one-year immutable cache policy. `index.html` remains `no-cache` so a deployment can point browsers at new hashes.
- Route modules and Recharts stay dynamically imported. This reduces initial parsing without removing routes or changing deep-link behavior.
- JetBrains Mono is served from the application bundle with `font-display: swap`, eliminating a render-blocking third-party request and keeping air-gapped deployments deterministic.

## Constraints and failure modes

- Middleware ordering must not add `Content-Encoding` to `/assets/*`, `/backend-api/*`, `/v1/*`, websocket handshakes, or ranged responses.
- Lazy loading must preserve all existing fork routes and named exports. A blank Suspense fallback is acceptable because the existing layout remains rendered while the route chunk loads.
- Immutable caching is safe only for content-hashed assets; applying it to `index.html` would strand clients on stale entry metadata.
- The bundled font files are binary source assets and must be included in the port and release artifact.

## Measurement method

Build the frontend from the branch base and again after the port using the same Bun lockfile and Vite production mode. Compare the generated entry chunk, total JavaScript bytes, gzip-compressed JavaScript bytes, modulepreload graph, and references to Google Fonts. Record both raw and gzip sizes so the result does not depend on browser caching or network instrumentation.

### Fork baseline (`97c717c1`)

- Production build: 26 JavaScript files, 1,833,783 raw bytes and 506,844 gzip bytes in total.
- Initial entry chunk: 774,559 raw bytes and 205,553 gzip bytes.
- Initial entry graph: 7 JavaScript files, 1,663,068 raw bytes and 456,126 gzip bytes.
- The entry document modulepreloads `vendor-charts-DazlBwCt.js` (580,350 raw bytes in Vite's report).
- The entry document contains Google Fonts preconnects plus a render-blocking JetBrains Mono stylesheet.

### Optimized build

- Production build: 63 JavaScript files, 1,852,605 raw bytes and 530,756 gzip bytes in total.
- Initial entry chunk: 354,822 raw bytes and 109,580 gzip bytes, reductions of 419,737 raw bytes (54.2%) and 95,973 gzip bytes (46.7%).
- Initial entry graph: 9 JavaScript files, 706,488 raw bytes and 218,204 gzip bytes, reductions of 956,580 raw bytes (57.5%) and 237,922 gzip bytes (52.2%).
- Neither the entry document nor the entry chunk statically references Recharts or `vendor-charts`; chart and route code remain in on-demand chunks.
- The build contains the bundled Geist Sans and JetBrains Mono WOFF2 assets and no Google Fonts origin references.
- The split build increases all-route JavaScript by 18,822 raw bytes (1.0%) and 23,912 gzip bytes (4.7%) because more chunk boundaries add wrapper and compression overhead. The delivery benefit is the smaller initial graph, not a smaller sum of every route artifact.

## Concrete example

An operator opening `/dashboard` receives a revalidated `index.html`, identity-encoded cacheable content-hashed assets with complete content lengths, and only the dashboard route's JavaScript. Visiting `/reports` then fetches the reports chunk on demand. A request to `/backend-api/codex/responses` remains uncompressed and streaming, while a normal `/api/dashboard/overview` JSON response may be gzip encoded when it exceeds the minimum size.

## Related contract

Normative requirements and scenarios live in `specs/frontend-architecture/spec.md` within this change.
