## ADDED Requirements

### Requirement: Accounts import accepts multiple auth files

The Accounts Import dialog SHALL accept one or more `auth.json` files and SHALL import them sequentially through `POST /api/accounts/import`, one request per file, without issuing requests in parallel. A failure for one file SHALL NOT prevent the remaining files from being imported. While a batch runs the dialog SHALL NOT be dismissible and its file input and submit control SHALL be disabled.

#### Scenario: All files import

- **WHEN** the operator selects two valid files and submits
- **THEN** the app sends two import requests one after the other
- **AND** the account queries are refreshed once and the dialog closes

#### Scenario: One file fails

- **WHEN** the operator selects three files and the second is rejected by the server
- **THEN** the first and third files are still imported

### Requirement: Multi-file import reports per-file results and refreshes once

After a batch the dashboard account queries SHALL be refreshed once if at least one file imported and not at all if every file failed. When every file imported the dialog SHALL close. When any file failed the dialog SHALL remain open, list each failed file with its error message, and keep only the failed files selected for retry.

#### Scenario: Partial failure keeps failed files for retry

- **WHEN** the second of three selected files is rejected
- **THEN** the dialog stays open showing the second file's name and error
- **AND** only the second file remains selected

#### Scenario: Every file fails

- **WHEN** every selected file is rejected
- **THEN** no account query refresh is issued
- **AND** each file's error is shown in the dialog
