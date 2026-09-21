## Context

Both public image handlers in `app/modules/proxy/api.py` pass a configured host
model to the existing Responses translators. The translators keep the public
`gpt-image-*` model in the `image_generation` tool and put the host in the outer
Responses `model` field.

Upstream PR [#2320](https://github.com/Soju06/codex-lb/pull/2320), commit
`92c7f6201a8fd31d6160570f60ee59db5686dd67`, provides
`app/core/openai/host_models.py`. Its registry APIs already exist in this fork.
The fork constraints in
[proxy admission ops notes](../../specs/proxy-admission-control/ops.md) exclude
upstream model-source routing and load-balancer decomposition. Only image host
selection is being ported.

## Goals / Non-Goals

Goals:

- Choose a current internal Responses host for both image routes without an
  operator override.
- Preserve the public `gpt-image-2` default, image payloads, accounting, policy,
  and request-log identity.
- Add public-route regressions whose fake upstream rejects the previous default
  host and completes image generation or editing when Luna is selected.

Non-goals:

- No account-probe changes, catalog discovery changes, model-source routes,
  load-balancer decomposition, retry-policy changes, or auth changes.
- No OMP source changes, live configuration edits, deployment, or live requests.
- No tests, builds, lint, format, or validation runs in this assignment. Record
  those as pending parent verification, not completed evidence.

## Decisions

### Port the existing resolver without new routing machinery

Add `resolve_default_host_model() -> str` in
`app/core/openai/host_models.py`, using the upstream candidate order
`gpt-5.6-luna`, then `gpt-5.5`. For each candidate, use
`get_model_registry().plan_types_for_model(slug)` and
`is_suppressed_model(slug)`. Select the first with non-empty plan visibility and
no suppression. If neither qualifies, return Luna.

The resolver reads the existing in-memory registry, including its bootstrap
fallback semantics. It performs no discovery, network request, account probe,
or retry. Catalog visibility is not account entitlement; normal account
selection remains authoritative after a host is chosen.

Changing only the setting's default would retain an obsolete override and would
not follow catalog visibility. A new per-route or configurable preference list
would duplicate the upstream contract without a requirement for it.

### Limit integration to the image handlers

Replace the two `settings.images_host_model` reads with the resolver. Keep the
explicit `host_model` translator argument and leave all public-model policy,
reservation, usage settlement, and observability code unchanged. Remove only
the obsolete settings field and its comments. Do not add an alias or migration
shim.

### Exercise real public routes with a rejecting upstream stub

Use the established account-import and `core_stream_responses` test pattern.
Control registry visibility without mocking the host resolver itself. The fake
upstream returns an error for an unacceptable host and a completed image for
the accepted host. Exercise both JSON generation and multipart edits for Luna
preference, hidden Luna, and suppressed Luna. Cover the neither-visible default
with a resolver test rather than fabricating account entitlement for a successful
route. Assert usable public image output and retain existing policy/accounting
tests.

For example, when both candidates have plan visibility, a
`POST /v1/images/generations` request with `model: gpt-image-2` uses Luna as the
outer Responses model and `gpt-image-2` as the tool model. If Luna lacks plan
visibility while `gpt-5.5` remains visible and unsuppressed, the same request
uses `gpt-5.5` internally.

## Risks / Trade-offs

- A visible candidate may not be entitled for a selected account. Leave existing
  account routing and error handling intact rather than treating registry
  visibility as authorization.
- The final Luna default may itself be unavailable or suppressed. This preserves
  the specified upstream default; it does not override suppression in account
  selection or guarantee image success.
- Operators may retain an obsolete override. Update existing related OpenSpec
  context and ops notes, but do not mutate live configuration.
- The existing OpenSpec config emits an unknown `context_docs` artifact-rule
  warning during instructions. Keep that unrelated configuration unchanged;
  artifact status is not strict validation.

## Migration Plan

Prepare proposal, design, spec delta, and tasks before editing application code.
Then port the helper, wire both routes, remove the setting, and update focused
regressions and existing related documentation.

The parent must run the focused suites and strict change validation before
claiming readiness. Any later authorized rollout should remove obsolete host
setting overrides. A rollback would revert this source change and restore its
previous configuration contract. Neither deployment nor rollback is performed
here.

## Open Questions

None for implementation. Test execution, strict spec validation, and any live
acceptance remain outside this assignment.
