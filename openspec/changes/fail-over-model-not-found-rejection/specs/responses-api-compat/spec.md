## ADDED Requirements

### Requirement: model_not_found is health-neutral and may move once before acceptance

A pre-acceptance upstream rejection with the exact error code `model_not_found` MUST NOT write an error record or bench the serving account. Before response acceptance, the proxy MUST give it at most one replacement-account attempt under the same rules as the stale account/model rejection, and MUST NOT move requests pinned by file ownership or hard continuity ownership. When no replacement can answer, the original envelope MUST be surfaced.

#### Scenario: HTTP stream fails over without a health penalty

- **WHEN** the first account answers HTTP 404 `model_not_found` before output and another account exists
- **THEN** the request completes on the other account
- **AND** no error is recorded against the rejecting account and it stays active.

#### Scenario: File-pinned request stays on its owner

- **WHEN** a file-pinned stream request receives `model_not_found` from the owner
- **THEN** only the owner is dispatched, the 404 `model_not_found` envelope is surfaced, and no error is recorded.

#### Scenario: Compact surfaces the rejection health-neutrally

- **WHEN** a compact request receives `model_not_found`
- **THEN** the 404 envelope is surfaced and no error is recorded against the account.
