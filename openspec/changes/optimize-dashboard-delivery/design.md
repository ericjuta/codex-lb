## Context

The fork and upstream have diverged substantially, but the three selected upstream commits touch an isolated dashboard-delivery surface. The fork currently serves SPA files directly from FastAPI, statically imports every page from `App.tsx`, forces Recharts into a manual vendor chunk, and loads JetBrains Mono from Google Fonts. The port must preserve fork-only routes and features while adopting only the delivery mechanics.

## Goals / Non-Goals

**Goals:**

- Reduce initial and repeat dashboard transfer and parsing cost.
- Keep proxy streaming and websocket paths semantically unchanged.
- Make the dashboard fully self-contained for offline and restricted-egress deployments.
- Preserve every existing fork route, page, translation, and settings surface.
- Produce reproducible before/after production-build evidence.

**Non-Goals:**

- Redesigning dashboard navigation or page content.
- Changing proxy payloads, API schemas, database state, or deployment configuration.
- Importing upstream's unrelated OpenSpec archive history.

## Decisions

1. Add a narrow ASGI dispatcher that wraps only `/api/` requests in Starlette `GZipMiddleware`. Static `FileResponse` bodies under `/assets/` remain identity encoded because Starlette streams their gzip representation without a content length, which some reverse proxies terminate before forwarding the body. This also avoids global compression around proxy SSE streams and websocket traffic. A `Range` request uses the original app so byte offsets remain valid.
2. Cache the `StaticFiles` resolver per static root and assign immutable caching only to Vite's content-hashed `assets/` namespace. The SPA document remains `no-cache`.
3. Convert each existing page import in the fork's `App.tsx` to an equivalent `React.lazy` import without changing the route table. Wrap the `Outlet` once at the layout boundary.
4. Keep every Recharts export behind the existing lazy wrapper and remove the manual Recharts chunk. Let Rollup construct a dynamic charts graph instead of hoisting shared chart helpers into the entry graph.
5. Bundle the upstream JetBrains Mono variable-font subsets under `frontend/public/fonts` and declare them locally with `font-display: swap`. No new dependency or runtime fetch is introduced.
6. Consolidate the upstream changes under one fork-local OpenSpec change. Source commits remain attributable in git history, while requirements and rationale follow the fork's current documentation policy.

## Risks / Trade-offs

- **[Compression changes response framing]** → Compress only bounded dashboard API responses; serve static assets with their original content length and cover dashboard, proxy, and ranged-asset behavior in integration tests.
- **[Lazy routes briefly render no page body]** → Keep the persistent layout visible and use the upstream blank fallback; route failures still surface through existing application error handling.
- **[Immutable caching could retain stale content]** → Apply it only below Vite's content-hashed `assets/` path and keep `index.html` revalidated.
- **[Binary font provenance or packaging is missed]** → Port exact upstream assets, verify build output contains them, and verify generated HTML/CSS has no Google Fonts references.
- **[Fork routes are accidentally dropped]** → Adapt imports in place and exercise the full frontend suite rather than replacing `App.tsx` wholesale.

## Migration Plan

Deploy as a normal application build. No environment, database, or operator migration is required. Rollback is a commit revert; cached hashed assets remain harmless because the rolled-back `index.html` references its own asset hashes.

## Open Questions

None. The three source patches are isolated and their applicability was checked against the branch base before implementation.
