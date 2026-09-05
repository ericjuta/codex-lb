# API-key secret response context

## Decision

Inject FastAPI `Response` into create/regenerate handlers and set the existing
credential export policy only after successful service operations:

- `Cache-Control: no-store, no-cache, must-revalidate, private`
- `Pragma: no-cache`
- `Expires: 0`

Typed Pydantic responses remain unchanged. Error paths never receive secret
headers or a plain key.

## Constraints

- Cover the fork's canonical create URL (`POST /api/api-keys/`) and regeneration.
  This fork does not expose a slashless `POST /api/api-keys` alias; do not add
  one just to match upstream tests.
- Do not apply to list/update/delete.
- Preserve write authorization and secret-free application/audit logs.
