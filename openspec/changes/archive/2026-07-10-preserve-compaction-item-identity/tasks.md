## 1. Preserve Proxy Compaction Identity

- [x] 1.1 Preserve a non-empty upstream compaction item ID in the shared Codex-affinity compact-result normalizer without inventing an ID.
- [x] 1.2 Update direct compact and terminal-trigger response tests to prove ID preservation and ID-less fallback behavior.

## 2. Harden the Codex Client

- [x] 2.1 Prevent the adjacent Codex client from synthesizing missing IDs for opaque compaction response items while retaining supplied upstream IDs.
- [x] 2.2 Add Codex core regression coverage with `item_ids` enabled for both missing and supplied compaction IDs.

## 3. Verify Contracts

- [x] 3.1 Run focused codex-lb tests, lint/type checks for touched Python files, and strict OpenSpec validation.
- [x] 3.2 Run Codex formatting and focused `codex-core` tests, then inspect both repositories' final diffs and statuses.
