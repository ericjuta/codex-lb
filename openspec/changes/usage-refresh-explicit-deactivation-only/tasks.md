## 1. Policy and Implementation

- [x] 1.1 Remove HTTP-status-only deactivation from the shared usage-error classifier while preserving permanent-code and explicit-message handling.
- [x] 1.2 Audit all scoped usage-404 references and document whether any concrete account-not-found or payment-required terminal envelope exists.

### Upstream Verification (caad3d40)
- [x] Upstream validated the OpenSpec change and confirmed the delta replaces the full owning requirement.

## 2. Regression Coverage

- [x] 2.1 Invert the existing bare 402 behavior test and add bare 404 coverage for unchanged status, no persistence update, no routing-unavailable mark, and retained refresh-failure logging.
- [x] 2.2 Preserve regression coverage for permanent-failure status mapping and explicit deactivation-message handling.
- [x] 2.3 Cover the post-auth-refresh retry path with an ambiguous HTTP error.

## 3. Documentation

- [x] 3.1 Review published usage-refresh documentation and update it only if it currently describes failure/deactivation semantics.

## 4. Verification

### Upstream Verification (caad3d40)
- [x] Upstream ran the focused usage-updater tests and the full unit suite.
- [x] Upstream ran lint and type-check gates.
- [x] Upstream ran strict change validation and main-spec validation.

### Fork Verification
- [ ] 4.1 Run the focused usage-updater tests and the full unit suite.
- [ ] 4.2 Run lint and type-check gates, restoring `uv.lock` if the type checker mutates it.
- [ ] 4.3 Run strict change validation and main-spec validation, then verify implementation coherence against the change.

## 5. Delivery

Upstream-only (caad3d40); not claimed for this fork.

- [x] Upstream wrote `/tmp/usage404-report.md`.
- [x] Upstream committed the verified change on the feature branch.
