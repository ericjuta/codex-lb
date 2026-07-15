## 1. Baseline and contract

- [x] 1.1 Capture a production frontend baseline with raw/gzip JavaScript sizes, entry preload graph, and external-font references.
- [x] 1.2 Validate the proposal, design, normative delta spec, and narrative context before implementation.

## 2. Dashboard response delivery

- [x] 2.1 Port the dashboard-only gzip dispatcher, ranged-response bypass, static resolver cache, and immutable hashed-asset policy from `c01abcaf`.
- [ ] 2.2 Add and pass focused integration coverage for dashboard compression, cache headers, ranged assets, and proxy-route exclusion.

## 3. Frontend load boundaries

- [x] 3.1 Port route-level lazy loading and deferred Recharts chunking from `3e4479d9` and `c01abcaf` without dropping fork routes.
- [ ] 3.2 Verify the production entry graph excludes unvisited route modules and static/modulepreloaded Recharts code.

## 4. Self-hosted font

- [x] 4.1 Port the JetBrains Mono assets and local font declarations from `acfb295e` and remove Google Fonts references.
- [ ] 4.2 Verify the production build contains the local font files and no Google Fonts origin references.

## 5. Validation and evidence

- [ ] 5.1 Run frontend lint, typecheck, full tests, and production build; compare optimized bundle evidence with the baseline.
- [ ] 5.2 Run focused backend tests, Python lint/format checks for changed files, and strict OpenSpec validation.
- [ ] 5.3 Inspect the final diff, commit history, and worktree status; document remaining risks without pushing.
