## Tasks

- [x] Make `importMutation` import a list of files sequentially, collect per-file results, and refresh account queries once.
- [x] Let the Import dialog select multiple files, list them, and disable controls while a batch runs.
- [x] After a partial failure, show per-file errors and keep only the failed files selected; close on full success.
- [x] Remove the dialog's single `error` prop, which the per-file results replace.
- [x] Add dialog tests over the real mutation hook and a mocked import endpoint for sequential calls, partial failure, and total failure.
- [x] Run focused frontend tests, typecheck, eslint, and strict OpenSpec validation.
