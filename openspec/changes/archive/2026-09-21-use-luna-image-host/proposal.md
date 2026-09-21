# Use a current Luna-first host model for image routes

## Why

Both image routes currently default their internal Responses host to `gpt-5.5`
through `images_host_model`. Adopt the Luna-first selection from upstream PR
[#2320](https://github.com/Soju06/codex-lb/pull/2320), commit
`92c7f6201a8fd31d6160570f60ee59db5686dd67`, so that internal choice follows
catalog visibility without changing the public image model.

## What Changes

- Both image routes resolve the internal host from the existing model registry.
  Prefer `gpt-5.6-luna`, then `gpt-5.5`, requiring non-empty registry plan
  visibility and no suppression for each candidate.
- When neither candidate qualifies, select `gpt-5.6-luna`. This default is not
  evidence of account entitlement; existing account routing can still reject it.
- **BREAKING**: remove the `images_host_model` operator setting. Host selection
  becomes code-owned. Keep `images_default_model`, `images_max_partial_images`,
  and all other settings unchanged.
- The public contract is untouched: clients still send and receive
  `gpt-image-*`, and usage accounting, API-key policy, and request logging keep
  using the public model.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `images-api-compat`: select the internal host Responses model from registry
  visibility with a fixed preference order instead of an operator setting.

## Impact

- **Spec**: `images-api-compat`
- **Code**: new `app/core/openai/host_models.py`; both image handlers in
  `app/modules/proxy/api.py`; `images_host_model` removed from
  `app/core/config/settings.py`.
- **Operators**: remove obsolete `images_host_model` overrides during a separately
  authorized rollout. This assignment does not edit live configuration.
- **Unchanged**: account probes, model-source routes, load balancer selection,
  retry policy, auth, and the `images_service` translation signature
  (`host_model` stays an explicit argument).
