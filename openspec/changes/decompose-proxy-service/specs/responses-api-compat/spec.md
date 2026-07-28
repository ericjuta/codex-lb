## ADDED Requirements

### Requirement: Proxy service decomposition preserves compatibility

The proxy implementation MUST preserve the public `app.modules.proxy.service.ProxyService` import surface and externally observable proxy behavior while domain logic moves into the private `_service` package. Existing private `_support` and `_warmup` import paths MUST remain available through compatibility shims during the incremental migration.

#### Scenario: Existing callers use the stable façade

- **GIVEN** a caller imports `ProxyService` from `app.modules.proxy.service`
- **WHEN** the decomposed proxy implementation is loaded
- **THEN** the import succeeds without caller changes
- **AND** proxy requests retain their existing routing, retry, settlement, and response behavior

#### Scenario: Transitional private imports remain available

- **GIVEN** an internal caller still imports a moved name from `_support` or `_warmup`
- **WHEN** the compatibility shim is imported
- **THEN** it exposes the corresponding name from the private `_service` implementation
