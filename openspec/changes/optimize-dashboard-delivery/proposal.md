## Why

The fork still sends avoidable dashboard bytes on first load, depends on an external render-blocking font stylesheet, and eagerly loads every route. Porting the isolated upstream delivery optimizations improves startup and repeat navigation without changing proxy request semantics or removing fork-specific dashboard features.

## What Changes

- Compress dashboard JSON and static assets while explicitly excluding proxy streaming routes and ranged asset responses.
- Cache Vite content-hashed assets immutably while keeping the SPA entry document revalidated.
- Keep charting code and dashboard routes out of the initial JavaScript graph until the user visits the corresponding surface.
- Self-host JetBrains Mono and remove the dashboard's Google Fonts dependency.
- Add focused regression coverage and record reproducible bundle evidence for the fork baseline and optimized build.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-architecture`: Define the dashboard delivery, route-loading, asset-caching, and self-hosted-font contracts.

## Impact

- Backend: dashboard-only ASGI middleware and SPA static-file response headers.
- Frontend: route imports, Recharts loading, Vite chunking, font declarations, and bundled font assets.
- Tests: dashboard compression/cache integration coverage plus frontend lint, typecheck, test, and build verification.
- Dependencies/APIs: no new runtime service, public API, database, or environment-variable requirement.
