# github-automation Specification

## Purpose
Repository automation around the Codex review merge gate: the `Codex review labels` workflow and its synchronization script keep `🤖 codex: ok` / `🤖 codex: needs work` labels faithful to current-head CI state and Codex review evidence, keep `needs rebase` faithful to confirmed merge-conflict state, and use token sourcing that stays within GitHub API quotas and degrades safely when privileged credentials are unavailable.
## Requirements
### Requirement: Needs-rebase label sync

The Codex label synchronization script MUST add `needs rebase` when GitHub
reports a confirmed merge conflict, MUST remove it when GitHub reports a known
mergeable or non-conflict state, and MUST preserve its current value only when
GitHub reports `UNKNOWN`. It MUST NOT infer a conflict from the pull request
merely being behind the base branch.

#### Scenario: Confirmed conflict gains the label

- **WHEN** GitHub reports the pull request as `CONFLICTING` or `DIRTY`
- **THEN** the synchronizer adds `needs rebase`

#### Scenario: Review-blocked pull request loses a stale label

- **GIVEN** a pull request has `needs rebase`
- **WHEN** GitHub reports it as `BLOCKED` by review or status requirements
- **THEN** the synchronizer removes `needs rebase`

#### Scenario: Base lag alone removes a stale label

- **WHEN** GitHub reports a pull request as `BEHIND` without a confirmed conflict
- **THEN** the synchronizer removes `needs rebase` when present
- **AND** it does not add the label to an unlabelled pull request

#### Scenario: Other mergeable statuses remove a stale label

- **GIVEN** a pull request has `needs rebase`
- **WHEN** GitHub reports `CLEAN`, `DRAFT`, `HAS_HOOKS`, or `UNSTABLE`
- **THEN** the synchronizer removes `needs rebase`

#### Scenario: Unknown state preserves current evidence

- **WHEN** GitHub reports `UNKNOWN`
- **THEN** the synchronizer preserves the current `needs rebase` value

### Requirement: Codex review label sync write-token fallback

The `Codex review labels` workflow MUST execute the label synchronization script from the trusted default branch and MUST prefer a dedicated GitHub App installation token, then a repository-provided write token, before falling back to the default `github.token`.

#### Scenario: GitHub App credentials are configured

- **WHEN** the repository defines the `CODEX_LABEL_SYNC_APP_ID` variable and the `CODEX_LABEL_SYNC_APP_PRIVATE_KEY` secret
- **THEN** the workflow mints a short-lived installation token for that App before the sync step
- **AND** the mint requests only the label-sync permission subset (actions write, checks read, contents read, issues write, pull requests read, statuses read) rather than inheriting all installation permissions
- **AND** the sync step uses that token ahead of `CODEX_LABEL_SYNC_TOKEN`, `RELEASE_PLEASE_TOKEN`, and `github.token`

#### Scenario: App token mint fails or is not configured

- **WHEN** the mint step fails, or the `CODEX_LABEL_SYNC_APP_ID` variable is absent
- **THEN** the job does not fail because of the mint step
- **AND** the sync step falls back to the next available token in the chain

#### Scenario: Privileged token is configured

- **WHEN** the workflow synchronizes Codex review labels and no App token was minted
- **THEN** it uses `CODEX_LABEL_SYNC_TOKEN` when present
- **AND** it falls back to `RELEASE_PLEASE_TOKEN` before `github.token`
- **AND** it checks out the default branch with persisted checkout credentials disabled

### Requirement: Codex review label sync write-denial resilience

The Codex label synchronization script MUST distinguish GitHub write-permission denials from classification/read failures.

#### Scenario: GitHub App token cannot mutate a PR resource

- **WHEN** a label, comment, or workflow-run approval write returns `Resource not accessible by integration (HTTP 403)`
- **THEN** the workflow logs a per-PR warning for the skipped mutation
- **AND** it continues processing remaining selected PRs
- **AND** it exits successfully if no read/classification errors occurred

#### Scenario: PR state cannot be read or classified

- **WHEN** the script cannot read required PR state, check state, merge state, or Codex review evidence
- **THEN** the workflow fails rather than silently treating the PR as synchronized

### Requirement: Codex review label sync review-thread state

The Codex label synchronizer MUST grant `🤖 codex: ok` only for a head with green required checks, a clean Codex review, and no unresolved current-head Codex findings. Unresolved, non-outdated current-head inline findings MUST count as needs-work evidence. Resolved or outdated threads MUST NOT count. An unresolved thread MUST count as current-head only if its current commit, original commit, or body text ties it to that head. Otherwise, stale unresolved inline threads MUST remain non-blocking.

#### Scenario: Resolved inline finding no longer blocks the ok label

- **WHEN** a current-head inline Codex finding comment belongs to a resolved
  review thread
- **AND** a clean current-head Codex review exists
- **THEN** the script does not classify that inline finding as active
  needs-work evidence

#### Scenario: Unresolved inline finding still blocks the ok label

- **WHEN** a current-head inline Codex finding comment belongs to an unresolved,
  non-outdated review thread
- **THEN** the script classifies that inline finding as active needs-work
  evidence

#### Scenario: stale rebased inline thread remains unresolved

- **GIVEN** a pull request was rebased after a Codex inline finding
- **AND** the unresolved GraphQL review thread still reports `isOutdated=false`
- **AND** the thread's current commit is not the current head
- **AND** the thread's original commit is not the current head
- **AND** the thread body does not mention the current head
- **WHEN** the label synchronizer evaluates the pull request
- **THEN** that thread does not force `🤖 codex: needs work`

#### Scenario: reanchored unresolved inline thread belongs to the current head

- **GIVEN** an unresolved Codex inline finding thread
- **AND** the thread's current commit is the pull request head
- **AND** the thread's original commit is older than the pull request head
- **WHEN** the label synchronizer evaluates the pull request
- **THEN** that thread blocks `🤖 codex: ok`
- **AND** the synchronizer records a needs-work reason that links to the thread

#### Scenario: unresolved inline thread belongs to the current head

- **GIVEN** an unresolved Codex inline finding thread
- **AND** the thread's original commit is the pull request head
- **WHEN** the label synchronizer evaluates the pull request
- **THEN** that thread blocks `🤖 codex: ok`
- **AND** the synchronizer records a needs-work reason that links to the thread

#### Scenario: unresolved inline thread mentions the current head explicitly

- **GIVEN** an unresolved Codex inline finding thread
- **AND** the thread body mentions the current pull request head
- **WHEN** the label synchronizer evaluates the pull request
- **THEN** that thread blocks `🤖 codex: ok`
- **AND** the synchronizer records a needs-work reason that links to the thread

#### Scenario: resolved inline thread is resynchronized by the scheduled fallback

- **GIVEN** a pull request has a `🤖 codex: needs work` label from an unresolved Codex inline finding
- **WHEN** that review thread is resolved
- **THEN** the scheduled Codex label synchronization run resynchronizes the open pull request's labels

### Requirement: Codex review labels use the authoritative current-head CI suite

The Codex review label synchronizer SHALL identify CI by the latest `CI Required` check. Its newest same-head run SHALL be authoritative even before its own check appears. Ordering SHALL use attempt start time, then run creation time, check recency, and run id. Only older runs' Actions checks in that workflow, including stale required contexts, MUST be ignored. Authoritative-run checks, unattributed checks, non-Actions statuses, and independent-workflow failures remain blocking evidence.

#### Scenario: Cancelled duplicate leaves a unique failed placeholder

- **GIVEN** an older CI workflow run for the current head was cancelled
- **AND** that run left a uniquely named non-required matrix placeholder in failure
- **AND** a newer run for the same head completed every required check including `CI Required` successfully
- **WHEN** Codex review labels are synchronized
- **THEN** the stale placeholder does not make the current head failed
- **AND** the synchronizer may request or accept current-head Codex review evidence

#### Scenario: Authoritative CI run has an optional failure

- **GIVEN** the newest run of the CI workflow identified by the latest `CI Required` check is the authoritative run
- **AND** another check in that same run failed
- **WHEN** Codex review labels are synchronized
- **THEN** the current head remains classified as failed

#### Scenario: A newer run stays pending until its own CI Required completes

- **GIVEN** an older run of the CI workflow completed `CI Required` successfully for the current head
- **AND** a newer run of the same CI workflow was created for the same head
- **AND** the newer run has started early checks but has not yet completed its own `CI Required` check
- **WHEN** Codex review labels are synchronized
- **THEN** the newer run is the authoritative CI suite and the older run's completed checks are ignored
- **AND** the current head remains classified as pending until the newer run's `CI Required` completes

#### Scenario: An older workflow run id is manually rerun

- **GIVEN** a newer-created CI workflow run completed successfully for the current head
- **AND** an older workflow `run_id` is manually rerun afterward
- **WHEN** the older run's new attempt has the latest `run_started_at`
- **THEN** that rerun is the authoritative CI suite
- **AND** its pending or failed checks remain blocking evidence

#### Scenario: Independent workflow on the same head fails

- **GIVEN** the authoritative CI workflow run is successful
- **AND** a different GitHub Actions workflow has a failed check on the same head
- **WHEN** Codex review labels are synchronized
- **THEN** the independent workflow failure remains blocking

### Requirement: Codex label sync MUST use check-run recency evidence

When multiple check runs have the same context name on a pull-request head, the label synchronizer MUST classify the current context from the newest run by
start or creation time. Completion time MUST NOT let an older superseded run
override a newer rerun that has already started.

#### Scenario: older duplicate run completes after a newer rerun starts

- **GIVEN** two check runs share the same name
- **AND** the older run started first but completes after the newer run starts
- **WHEN** the label synchronizer deduplicates check runs
- **THEN** it keeps the newer run
- **AND** a pending newer run keeps the pull request check state pending instead of failed

### Requirement: CI required check contexts remain stable under path filtering

The CI workflow SHALL create every branch-protection-required check context for
pull requests even when path filters determine that the expensive implementation
for a subsystem is unrelated to the change.

#### Scenario: non-backend pull request still creates pytest matrix contexts

- **GIVEN** a pull request changes no backend paths
- **AND** the repository ruleset requires `Tests (pytest, unit)`, `Tests (pytest, integration-core)`, `Tests (pytest, integration-bridge)`, and `Tests (pytest, e2e)`
- **WHEN** the CI workflow runs
- **THEN** each required pytest matrix check context is created
- **AND** each context completes successfully via a placeholder step
- **AND** the real pytest setup and test commands are skipped for that non-backend change

#### Scenario: backend pull request runs the real pytest slices

- **GIVEN** a pull request changes backend paths
- **WHEN** the CI workflow runs
- **THEN** each required pytest matrix check context runs its corresponding `make test-*` target
- **AND** the placeholder step is skipped

### Requirement: Simplicity budgets are enforced mechanically in CI

The repository SHALL define at least these budgets in `.github/simplicity-budgets.toml`:
- `README.md` lines, excluding the generated `ALL-CONTRIBUTORS-LIST` block and its markers.
- `README.md` h1/h2 headings, excluding fenced code.
- `.env.example` lines.
- Dashboard core-navigation items, with their source file and array name.

Budget increases require manifest edits under the `contribution-simplicity` principles.

#### Scenario: README grows past its line budget

- **GIVEN** a pull request whose `README.md`, after removing the
  `ALL-CONTRIBUTORS-LIST` block, exceeds `readme.max_lines`
- **WHEN** the Simplicity budgets workflow runs
- **THEN** the check prints the measured and budgeted values, emits an error
  annotation for `README.md`, and exits non-zero

#### Scenario: Shell comments inside fenced code blocks are not headings

- **GIVEN** a `README.md` containing `# comment` lines inside fenced code
  blocks
- **WHEN** the checker counts top-level headings
- **THEN** lines inside fenced code blocks are not counted
- **AND** fences using ` ``` ` or `~~~`, indented up to 3 spaces, are
  recognized, and a fence is closed only by a fence line using the same
  character
- **AND** only h1 and h2 heading lines outside fences count against
  `readme.max_top_level_headings`

### Requirement: Simplicity budget workflow runs independently

A dedicated `Simplicity budgets` workflow, separate from main CI, SHALL run the stdlib-only `.github/scripts/check_simplicity_budgets.py` on pull requests (including `labeled`/`unlabeled`), pushes to `main`, and `merge_group` events. The check SHALL fail on any exceeded budget.

#### Scenario: All budgets within limits

- **WHEN** every measured value is at or below its configured budget
- **THEN** the check prints each metric as `actual/budget OK` and exits 0

### Requirement: Nav budget refuses to pass when its target disappears

The budget checker MUST exit with configuration-error code 2 and an explicit
repoint instruction if the navigation source file or array configured in
`.github/simplicity-budgets.toml` `[core_nav]` is missing. Moving or renaming the
array MUST update `[core_nav]` in the same change for the check to pass.
The checker MUST also exit 2 if the manifest is missing or malformed, or a
`README.md` `ALL-CONTRIBUTORS-LIST:START` marker has no matching `END` marker.

#### Scenario: Nav array renamed without repointing the manifest

- **GIVEN** the configured nav array no longer exists in the configured file
- **WHEN** the checker runs
- **THEN** it exits with code 2
- **AND** the error message names the missing array and instructs updating
  `.github/simplicity-budgets.toml` in the same pull request

### Requirement: Simplicity budget override label

The checker SHALL read PR labels from `PR_LABELS`, a JSON array fetched at run time from the GitHub API, never the event payload. With `simplicity-budget-approved`, violations SHALL become warning annotations and the check SHALL exit 0 while printing every metric. The workflow MUST re-evaluate immediately on `labeled`/`unlabeled`. Failure messages MUST explain the override and that live label fetching makes reruns after labeling effective.

#### Scenario: Maintainer approves a temporary exceedance

- **GIVEN** a pull request over budget
- **WHEN** a maintainer applies the `simplicity-budget-approved` label
- **THEN** the `labeled` event starts a fresh check run that resolves the
  live label set from the API and sees the label (as would a manual re-run
  of the failed run)
- **AND** the run reports the violations as warning annotations and exits 0

### Requirement: Simplicity budget overrides are pull-request-only

Push and merge-group runs carry no PR labels and MUST NOT apply the override. Changes leaving `main` over budget MUST raise the budget in `.github/simplicity-budgets.toml` in the same diff.

#### Scenario: Label override does not launder main

- **GIVEN** a run triggered by a push to `main` or a `merge_group` event
- **WHEN** a budget is exceeded
- **THEN** no pull-request label set is resolved and the check fails
  regardless of any label on the originating pull request
