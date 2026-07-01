## ADDED Requirements

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
