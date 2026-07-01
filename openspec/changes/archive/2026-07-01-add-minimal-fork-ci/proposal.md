# Change: add minimal fork CI

## Why

Commit `c5d8ae70` removed every workflow under `.github/workflows/` from the
fork, so no automation runs the test suite or linter on pushes and pull
requests. The suite was brought back to fully green (4206 passed) at
`fdcd3418`, but nothing guards that state: a regression on `main` would go
unnoticed until someone runs pytest locally.

## What Changes

- Add a single minimal workflow `.github/workflows/ci.yml`: on pushes to
  `main` and on pull requests, sync dependencies with `uv sync --frozen`
  (CPython 3.14, matching the development environment) and run
  `uv run ruff check .` followed by `uv run pytest -q -n auto`.
- Enforce `ruff check` only. `ruff format --check` is intentionally NOT
  enforced: 21 files are unformatted from upstream history, and reformatting
  them wholesale would create needless conflicts on every future upstream
  rebase.
- Superseded runs on the same ref are cancelled via a concurrency group.

## Impact

Pushes to `main` and PRs get an automated green/red signal again. Known
pre-existing drift, out of scope here: the `github-automation` capability
spec still describes the deleted `Codex review labels` workflow; those
requirements refer to automation the fork no longer ships.
