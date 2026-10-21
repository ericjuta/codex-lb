## Why

Moving many accounts into the dashboard means opening the Import dialog once per
`auth.json` file, and each file shows its own toast and refreshes the dashboard
queries. The dialog also accepts only one file.

## What Changes

- The Import dialog accepts several `auth.json` files and imports them one at a
  time through the existing `POST /api/accounts/import` endpoint. No backend change.
- A failed file does not stop the remaining files. After the batch the dialog
  lists each failed file with its error and keeps only those files selected so the
  operator can retry them; it closes when every file imported.
- The account-related queries are invalidated once after the batch, and the batch
  reports one success toast and one failure toast instead of one toast per file.

## Impact

- Affected spec: `frontend-architecture` (Accounts page import).
- Affected code: Accounts import dialog, `importMutation` in `use-accounts.ts`,
  and their tests. `importMutation` now takes `File[]` and resolves to per-file results.
