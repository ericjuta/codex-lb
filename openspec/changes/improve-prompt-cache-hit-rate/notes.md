# Change notes: improve-prompt-cache-hit-rate

## Validation findings (2026-07-13, task 4.4)

### Structural fixes verified live
- Sticky affinity essentially perfect post-deploy: 94 hits / 5 new /
  1 fallback (prompt_cache kind), zero account crossings observed in a
  23-turn luna session.
- Multiproc metrics wiring (`PROMETHEUS_MULTIPROC_DIR`) makes `:9090`
  fleet-accurate across all uvicorn workers; per-model counters match
  postgres request_logs.
- Prewarm cache-pressure gate deployed; `skipped_cache_pressure` not yet
  observed (no account reached 2 concurrent large families during the
  soak window).

### Per-model cached/input (65-min soak)
| model | kind | input | cached | ratio |
|---|---|---|---|---|
| gpt-5.3-codex-spark | normal | 3.69M | 732k | 0.198 |
| gpt-5.6-terra | normal | 1.89M | 127k | 0.067 |
| gpt-5.6-luna | normal | 1.65M | 0 | 0.000 |
| gpt-5.4-mini | normal | 1.06M | 35k | 0.033 |

### Root cause of luna's 0% cached ratio: upstream delta-mode, not routing
Conversation-archive capture of raw upstream `response.create` frames
(temporarily enabled `CODEX_LB_CONVERSATION_ARCHIVE_ENABLED`) shows:

- spark sessions replay the full growing transcript every turn;
  turn-over-turn payload common prefix is 92-98% -> prompt cache engages
  (~20% cached ratio).
- luna sessions send ONE full-history frame at session start (798k chars,
  196 items), then per-turn deltas of 1-2 new items
  (`custom_tool_call_output`) plus a `prompt_cache_key`; common prefix
  turn-over-turn is ~0%. Upstream folds deltas into server-side
  conversation state and bills the full folded context as input_tokens
  with cached_input_tokens=0.

Conclusion: luna's cached ratio is a property of the client's incremental
websocket mode and upstream usage accounting, not of codex-lb placement.
No further proxy-side action can move it. The D1/D2/D3 fixes remain
correct and protect replay-mode models (spark baseline 0.198).

Ruled out: hook/context injection (deltas are tool outputs, and hooks are
model-agnostic while only luna shows this shape); account crossings
(single-account 23-turn session still 0%).

### Operational notes
- Conversation archive was enabled only for this diagnosis and disabled
  again afterward. Latent upstream bug noticed: with multiple uvicorn
  workers, hourly archive gzip files interleave gzip members from
  different processes; readers must scan for gzip magic and decode
  members individually.
