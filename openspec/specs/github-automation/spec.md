# github-automation Specification

## Purpose
TBD - created by archiving change fix-codex-review-label-token. Update Purpose after archive.
## Requirements
### Requirement: Codex review label sync write-token fallback

The `Codex review labels` workflow MUST execute the label synchronization script from the trusted default branch and MUST prefer a repository-provided write token before falling back to the default `github.token`.

#### Scenario: Privileged token is configured

- **WHEN** the workflow synchronizes Codex review labels
- **THEN** it uses `CODEX_LABEL_SYNC_TOKEN` when present
- **AND** it falls back to `RELEASE_PLEASE_TOKEN` before `github.token`
- **AND** it checks out the default branch with persisted checkout credentials disabled

### Requirement: Codex review label sync write-denial resilience

The Codex label synchronization script MUST distinguish GitHub write-permission denials from classification/read failures.

#### Scenario: GitHub App token cannot mutate a PR resource

- **WHEN** a label, comment, or workflow-run approval write returns `Resource not accessible by integration (HTTP 403)`
- **THEN** the workflow logs a per-PR warning for the skipped mutation
- **AND** it continues processing remaining selected PRs
- **AND** it exits successfully if no read/classification errors occurred

#### Scenario: PR state cannot be read or classified

- **WHEN** the script cannot read required PR state, check state, merge state, or Codex review evidence
- **THEN** the workflow fails rather than silently treating the PR as synchronized

### Requirement: Fork CI runs lint and tests on main pushes and pull requests

The repository MUST provide a CI workflow that runs on every push to `main`
and on every pull request, and that fails when `ruff check` reports
violations or when the pytest suite reports failures or errors. The workflow
MUST install dependencies from the committed lockfile (`uv sync --frozen`) so
CI results reflect locked dependency versions. The workflow MUST NOT enforce
`ruff format --check` while upstream-inherited files remain unformatted.

#### Scenario: push to main runs the suite

- **WHEN** a commit is pushed to `main`
- **THEN** the CI workflow syncs locked dependencies and runs `ruff check`
  and the pytest suite
- **AND** the run fails if either step fails

#### Scenario: pull request gets a CI signal

- **WHEN** a pull request is opened or updated
- **THEN** the same lint and test steps run against the PR head
- **AND** superseded in-progress runs for the same ref are cancelled

