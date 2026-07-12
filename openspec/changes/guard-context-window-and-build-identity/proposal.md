# Proposal: Guard Context Overflow and Publish Build Identity

## Why

Recent live traffic produced 'context_length_exceeded' failures for
'gpt-5.3-codex-spark'. The proxy already has model context metadata, but
estimable oversized requests can still reach upstream before failing. Operators
also need a deterministic Git-SHA identity in the running image and health
responses after deployment.

## What Changes

- Reject estimable inline Responses payloads before upstream selection when they
  exceed a conservative fraction of the effective model context window.
- Preserve existing behavior for opaque prior-response, conversation, and file
  references whose full context is not locally knowable.
- Publish the build Git SHA as an OCI image revision label, runtime environment
  value, and HTTP response header.

## Impact

- Context overflow becomes a local OpenAI-compatible 400 error with no prompt
  or credential logging.
- Direct Docker and Makefile image builds pass the current checkout SHA.
- Existing health response JSON remains unchanged; build identity is exposed in
  'X-App-Build-SHA'.
