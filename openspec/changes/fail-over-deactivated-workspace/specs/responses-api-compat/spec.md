## ADDED Requirements

### Requirement: Deactivated workspaces are permanent account failures that fail over

When upstream rejects a request with the exact error code `deactivated_workspace`, the proxy MUST deactivate the serving account and, before any downstream-visible output and while another candidate remains, MUST fail the request over to a different account. A bare HTTP 402 without that code MUST NOT deactivate the account.

#### Scenario: Stream fails over and deactivates only the revoked workspace

- **WHEN** the first selected account's upstream stream raises HTTP 402 with `error.code = "deactivated_workspace"` before any output
- **AND** a second eligible account exists
- **THEN** the request completes on the second account
- **AND** only the first account is persisted as deactivated with the workspace-deactivated reason.

#### Scenario: File-pinned request does not cross accounts

- **WHEN** the request is pinned to a file-owning account and that account's workspace is deactivated
- **THEN** the proxy MUST surface the upstream error without selecting another account.

#### Scenario: Keyed request settles its reservation before the permanent health write

- **WHEN** an API-key request receives `deactivated_workspace`
- **THEN** the API-key reservation MUST settle before the permanent failure is written.

#### Scenario: Bare 402 does not deactivate

- **WHEN** upstream returns HTTP 402 without the `deactivated_workspace` code
- **THEN** the account MUST remain active.
