## MODIFIED Requirements

### Requirement: Bootstrap model catalog is available before refresh

Before the first successful upstream model-registry refresh, the system MUST
serve a conservative static catalog of known Codex model slugs from both
`GET /v1/models` and `GET /backend-api/codex/models`. This static catalog is a
bundled fallback for startup/offline paths; refreshed upstream model-registry
data remains the authoritative source once available. The bootstrap catalog MUST
include `gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-5.6-sol`,
`gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`,
`gpt-5.3-codex`, `gpt-5.3-codex-spark`, `gpt-5.2`, and `codex-auto-review`,
and MUST NOT invent unverified variant slugs such as `gpt-5.5-pro`, a bare
`gpt-5.6`, or a bare `gpt-6`.

#### Scenario: OpenAI-compatible models endpoint serves bootstrap slugs

- **GIVEN** the model registry has no refreshed upstream snapshot
- **WHEN** a client calls `GET /v1/models`
- **THEN** the response contains exactly the bootstrap model slugs
- **AND** the response includes `gpt-6-astra`, `gpt-6-sol`, and `gpt-6-luna`
- **AND** the response does not include `gpt-5.5-pro`, bare `gpt-5.6`, or bare `gpt-6`

#### Scenario: Codex-native models endpoint serves bootstrap metadata

- **GIVEN** the model registry has no refreshed upstream snapshot
- **WHEN** a client calls `GET /backend-api/codex/models`
- **THEN** entries such as `gpt-6-sol`, `gpt-6-luna`, `gpt-5.6-sol`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex`, `gpt-5.3-codex-spark`, and `codex-auto-review` include representative upstream metadata including client version, context-window, visibility, modality, plan-availability, and reasoning/verbosity fields where known

## ADDED Requirements

### Requirement: GPT-6 Sol and Luna bootstrap metadata matches the live upstream catalog

The `gpt-6-sol` and `gpt-6-luna` bootstrap catalog entries MUST mirror the
upstream catalog entries captured from `/backend-api/codex/models` with client
version `0.160.0` on 2026-09-23 for metadata fields codex-lb serves before
account catalogs are authoritative.

Both entries MUST carry: `visibility` `"list"`; `context_window` `272000`;
`max_context_window` `872000`; `minimal_client_version` `"0.155.0"`;
`prefer_websockets` `true`; `default_reasoning_level` `"medium"`;
`default_verbosity` `"low"`; input modalities `text` and `image`;
`tool_mode` `"code_mode_only"`; `multi_agent_version` `"v2"`;
`use_responses_lite` `true`; `apply_patch_tool_type` `"freeform"`;
`web_search_tool_type` `"text_and_image"`; `supports_image_detail_original`
`true`; `default_service_tier` `null`; a single `priority` service tier named
`"Fast"` with description `"1.5x speed"`; and `additional_speed_tiers`
containing `"fast"`.

`gpt-6-sol` MUST carry display name `"GPT-6-Sol"`, description
`"Workhorse model for coding and everyday work."`, `priority` `2`,
`node_repl_auto_review_required` `true`, and reasoning levels `low`, `medium`,
`high`, `xhigh`, `max`, and `ultra`.

`gpt-6-luna` MUST carry display name `"GPT-6-Luna"`, description
`"Fast and affordable model for easier tasks."`, `priority` `3`,
`node_repl_auto_review_required` `false`, and reasoning levels `low`, `medium`,
`high`, `xhigh`, and `max`; it MUST NOT advertise `ultra`.

#### Scenario: GPT-6 Sol and Luna appear in bootstrap catalog before refresh

- **GIVEN** the model registry has no refreshed upstream snapshot
- **WHEN** a client calls `GET /backend-api/codex/models`
- **THEN** the response contains `gpt-6-sol` and `gpt-6-luna`
- **AND** each entry reports `context_window=272000`, `max_context_window=872000`, and `minimal_client_version="0.155.0"`
- **AND** `gpt-6-sol` reports `priority=2` and `gpt-6-luna` reports `priority=3`

#### Scenario: GPT-6 Sol advertises ultra reasoning and Luna does not

- **GIVEN** the model registry has no refreshed upstream snapshot
- **WHEN** a client calls `GET /backend-api/codex/models`
- **THEN** `gpt-6-sol` advertises `low`, `medium`, `high`, `xhigh`, `max`, and `ultra`
- **AND** `gpt-6-luna` advertises `low`, `medium`, `high`, `xhigh`, and `max` without `ultra`
- **AND** both default to reasoning level `medium`

#### Scenario: GPT-6 Sol and Luna expose live service-tier metadata

- **GIVEN** the model registry has no refreshed upstream snapshot
- **WHEN** a client calls `GET /backend-api/codex/models`
- **THEN** `gpt-6-sol` and `gpt-6-luna` report `default_service_tier` as `null`
- **AND** each advertises a `priority` service tier named `Fast` with description `1.5x speed`
- **AND** each lists `fast` in `additional_speed_tiers`

#### Scenario: GPT-6 Sol and Luna bootstrap websocket preference is honored

- **GIVEN** the model registry has no refreshed upstream snapshot
- **WHEN** websocket preference is checked for `gpt-6-sol` or `gpt-6-luna`
- **THEN** the lookup returns true

### Requirement: GPT-6 bootstrap entries share the live GPT-6 plan set

The `gpt-6-astra`, `gpt-6-sol`, and `gpt-6-luna` bootstrap entries MUST each
advertise exactly the plan set returned by the live upstream catalog on
2026-09-23: `business`, `edu`, `edu_plus`, `edu_pro`, `education`, `ent26`,
`enterprise`, `enterprise_cbp_automation`, `enterprise_cbp_trial`,
`enterprise_cbp_usage_based`, `finserv`, `free`, `free_workspace`, `go`, `hc`,
`k12`, `plus`, `pro`, `prolite`, `promax`, `quorum`, `sci`,
`self_serve_business_prolite`, `self_serve_business_usage_based`, and `team`.

#### Scenario: GPT-6 bootstrap entries advertise the same plans

- **GIVEN** the model registry has no refreshed upstream snapshot
- **WHEN** a client calls `GET /backend-api/codex/models`
- **THEN** `gpt-6-astra`, `gpt-6-sol`, and `gpt-6-luna` report identical `available_in_plans` sets
- **AND** each set includes `ent26` and `promax`

#### Scenario: GPT-6 bootstrap plans admit ent26 and promax accounts before refresh

- **GIVEN** the model registry has no refreshed upstream snapshot
- **WHEN** account plan filtering runs for a `gpt-6-sol`, `gpt-6-luna`, or `gpt-6-astra` request
- **THEN** accounts on the `ent26` or `promax` plan are eligible

### Requirement: GPT-6 Sol and Luna expose their documented output budget

When serving `GET /v1/models`, the system MUST report `max_output_tokens`
`128000` for `gpt-6-sol` and `gpt-6-luna` in model metadata and compatibility
projections, and MUST NOT change their reported input context budget of
`272000`. The Codex-native `GET /backend-api/codex/models` entries MUST remain
unchanged by this projection.

#### Scenario: OpenAI-compatible Sol and Luna metadata exposes output budget

- **GIVEN** the model registry has no refreshed upstream snapshot
- **WHEN** a client calls `GET /v1/models`
- **THEN** the `gpt-6-sol` and `gpt-6-luna` entries each report `max_output_tokens=128000`
- **AND** each entry's input context budget remains `272000`

### Requirement: Fallback client version covers every bootstrap minimal client version

The default fallback Codex client version (`model_registry_client_version`)
MUST be `0.156.0` or newer and MUST be greater than or equal to the highest
`minimal_client_version` in the bootstrap catalog, currently `0.155.0` for
`gpt-6-sol` and `gpt-6-luna`, so a degraded-startup registry refresh still
receives every bootstrap model from upstream.

#### Scenario: Degraded-startup refresh still requests GPT-6 Sol and Luna

- **GIVEN** the live Codex release lookup fails and no version is cached
- **WHEN** the model registry refresh fetches `<base>/codex/models?client_version=<fallback>`
- **THEN** the fallback version is `0.156.0` or newer
- **AND** the fallback version is at least the highest bootstrap `minimal_client_version`
