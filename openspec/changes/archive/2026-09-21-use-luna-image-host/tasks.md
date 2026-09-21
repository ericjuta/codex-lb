## 1. Preparation

- [x] 1.1 Read project conventions and fork constraints; retrieve the helper from upstream PR #2320 commit `92c7f6201a8fd31d6160570f60ee59db5686dd67`.
- [x] 1.2 Create the `use-luna-image-host` proposal, design, spec delta, and tasks with the pinned OpenSpec 1.3.0 workflow before editing application code.

## 2. Implementation

- [x] 2.1 Port `resolve_default_host_model()` with Luna-first, visible/non-suppressed candidate selection and the Luna default.
- [x] 2.2 Use the resolver in both image routes without changing public-model policy, accounting, translation, retry, or auth.
- [x] 2.3 Remove the obsolete `images_host_model` setting and its active callers and stale test assertions; preserve all other settings.

## 3. Regression coverage and documentation

- [x] 3.1 Add public generation and multipart edit regressions whose fake upstream rejects the old host but accepts selected Luna.
- [x] 3.2 Cover hidden and suppressed Luna fallback to visible `gpt-5.5`, and default-to-Luna when neither candidate qualifies.
- [x] 3.3 Update existing related OpenSpec context and ops documentation, including obsolete host-configuration guidance, with upstream provenance and no live-proof claim.
- [x] 3.4 Inspect references and changed source to confirm no obsolete host-setting callers remain and no out-of-scope behavior changed.

## 4. Parent verification

- [x] 4.1 Run focused image route, image schema/translation, and OpenAI SDK compatibility tests.
- [x] 4.2 Run `bunx --package @fission-ai/openspec@1.3.0 openspec validate use-luna-image-host --strict`.
- [x] 4.3 Record actual test and validation results in this change and related ops notes; do not mark these complete from artifact status or source inspection.

Completed parent verification on 2026-09-21:

```sh
uv run pytest tests/integration/test_proxy_images.py tests/unit/test_images_schemas.py tests/unit/test_images_translation.py tests/e2e/test_openai_sdk_compat.py::TestImages
# 184 passed, 0 failed
bunx --package @fission-ai/openspec@1.3.0 openspec validate use-luna-image-host --strict
# Change 'use-luna-image-host' is valid
```

Both public-route regressions failed under fault injection of the prior
`gpt-5.5` host behavior. Ruff checks passed on the five changed Python files,
with all five already formatted. Targeted ty checks passed on the three
changed application files. Full repository suites were not run.

`bash ./update.sh` deployed the uncommitted local application changes. The
container was healthy, and all three deployed application files matched the
checkout. The LB envfile, effective environment, credentials, and runtime
settings were unchanged. This was not a clean-commit deployment. Nothing was
pushed or merged, and no remote deployment was performed.

A real OMP SDK session-wrapped `generate_image` smoke from the verified source
tree used `codex-lb/gpt-image-2` with provider fallbacks disabled. One generation
and one edit returned PNGs, visually confirmed as a red circle on white edited
to blue with composition retained. Both were 1254x1254 despite a 1024x1024 size
request. This proves local generation and editing, not exact-size control or
the actual upstream host slug. The separately installed OMP binary and image
role were verified in a fresh process. See the related ops notes for details.
