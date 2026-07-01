# Tasks

- [x] Add `.github/workflows/ci.yml` running `uv sync --frozen`,
      `uv run ruff check .`, and `uv run pytest -q -n auto` on pushes to
      `main` and on pull requests.
- [x] Confirm `uv run ruff check .` passes repo-wide so the lint gate starts
      green (fix any auto-fixable violations first).
- [ ] Push and confirm the first workflow run completes green on GitHub.
