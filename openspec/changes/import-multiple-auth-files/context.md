# Context

## Purpose

Import many exported account `auth.json` files in one dialog interaction.

## Upstream provenance

Hand port of upstream `a6ebfa6ae` (#2564). Differences from upstream:

- Upstream loops in the dialog and calls the single-file mutation per file, so it shows N toasts and
  refreshes N times. The fork moves the loop into `importMutation`, which gives one refresh and one
  toast per outcome. The fork's mutation hook owns invalidation, so this needed no new data-layer API.
- Upstream stops at the first failed file and leaves the remaining files selected. The fork continues
  past failures and keeps only the failed files, which are the ones still needing action.
- Skipped: upstream's locale keys (the fork's import dialog uses literal English strings), its
  main-spec edits, and its screenshots.

## Decisions

- Files are sent sequentially, never in parallel, because each import writes credentials and the
  endpoint is not designed for concurrent bursts.
- `importMutation` resolves instead of rejecting on per-file failures, so the dialog always receives the
  full outcome. The dialog's `error` prop and the page-level aggregation of `importMutation.error` were
  removed because they could no longer be set.
- When every file fails, no query refresh happens because nothing changed server-side.

## Failure modes

- A network drop mid-batch marks the current and later files as failed (each gets its own error) and
  keeps them selected for retry; files already imported are not re-sent.
- Re-importing an already imported file is handled by the existing endpoint, not by the dialog.

## Example

Selecting `a.json`, `b.json`, `c.json` where `b.json` is invalid imports `a` and `c`, refreshes the
account list once, toasts "2 accounts imported" and the failure message, and leaves `b.json` selected
with "b.json: <error>" shown in the dialog.
