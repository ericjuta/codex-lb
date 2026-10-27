# GPT-6.1 Terra support

## Purpose and scope

Add the new Terra model through the existing catalog, pricing and Cursor-alias paths. No other model changes or transport changes are included.

## Sources and decisions

Captured on 2026-10-27 from the running proxy's `/backend-api/codex/models?client_version=0.160.0`, excluding instruction payloads. Fetched upstream main `72630bbfe` lacks Terra bootstrap support; the fetched metadata branch lacks Terra pricing.

- [Official Terra model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-terra.md)
- [Official pricing](https://developers.openai.com/api/docs/pricing)

The Codex catalog advertises 500000 input/context tokens, 872000 maximum context, low default reasoning, and reasoning levels through ultra. Those Codex-specific values take precedence over different public API defaults. The documented output limit is 128000. Existing fallback client version 0.156.0 already covers the model's 0.153.0 minimum.

Terra cached input costs 5% of uncached input, not the 10% of older GPT-6 models. Long-context pricing begins above 272000 input tokens even though the Codex input window is 500000. Existing pricing machinery handles these rates without new branches.

## Example

`gpt-6.1-terra-high-fast` normalizes to Terra with high reasoning and priority service unless an explicit service tier overrides the speed suffix. Existing policy gives the reasoning suffix precedence over explicit effort; this change preserves that behavior. A standard request with 200000 input tokens (100000 cached) and 10000 output tokens costs an estimated USD 0.155.

## Verification

An isolated Uvicorn process using disposable SQLite and no repository dotenv configuration served readiness, `/v1/models`, and `/backend-api/codex/models` with HTTP 200. The OpenAI-compatible entry reported 500000 input/context and 128000 output. Every captured non-instruction native Terra field matched the bootstrap endpoint (plan order normalized).

Focused regression run: `tests/unit/test_model_registry.py`, `tests/unit/test_pricing.py`, `tests/unit/test_request_policy.py`, and `tests/integration/test_v1_models.py`: **221 passed**. Ruff lint passed for all eight changed Python files; its format check identified one test file, which was formatted. Strict validation of this OpenSpec change passed, with the inherited archive warning below. A separate billing/policy smoke computed USD 0.155 for the example and confirmed canonical Terra/high/flex for an alias with explicit low effort and flex tier. The isolated runtime was stopped after verification.

## Constraints and failure modes

Live registry refresh remains authoritative and may remove or change the model. Catalog discovery does not prove account entitlement or successful inference. API rate-card accounting is an estimate for subscription-backed usage; cache-write billing is outside the existing price model and this change. No production mutation, commit, push, deployment, or paid inference has been performed for this change.

The inherited duplicate requirement headings in the base `responses-api-compat` spec prevent normal archive/spec sync; keep this delta active rather than modifying unrelated historical requirements.
