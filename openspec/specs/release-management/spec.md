# release-management Specification

## Purpose
Describe beta release preparation and publication, prerelease artifact isolation from stable aliases, and release-please-owned stable promotion. This fork does not currently run the release-please workflow, so release-please-dependent steps require a separately maintained release process.
## Requirements
### Requirement: Beta releases are prepared through release PRs

An automatically maintained PR against `main` SHALL prepare beta releases by setting release-managed version files to `X.Y.Z-beta.N`. Preparation SHALL run after release-please completes and after pushes to `main`. It SHALL derive `X.Y.Z` from the open release-please PR branch, or do nothing if none exists. Beta PRs SHALL NOT update `.github/release-please-manifest.json`. Release-please retains stable version ownership.

#### Scenario: automation syncs the next beta from the release-please PR

- **GIVEN** release-please has opened or updated `release-please--branches--main` with `pyproject.toml` version `1.19.0`
- **WHEN** the beta PR sync workflow runs
- **THEN** it creates or updates a pull request that sets release-managed files to `1.19.0-beta.N`
- **AND** `N` is one higher than the highest existing `v1.19.0-beta.N` tag
- **AND** `.github/release-please-manifest.json` remains unchanged

#### Scenario: automation is idle without a release-please PR

- **GIVEN** there is no open release-please PR targeting `main`
- **WHEN** the beta PR sync workflow runs
- **THEN** it exits without creating a beta release pull request

#### Scenario: automation ignores forked release-please branch names

- **GIVEN** a fork has an open pull request whose head branch is named `release-please--branches--main`
- **WHEN** the beta PR sync workflow looks for the release-please PR
- **THEN** it ignores that pull request unless the head repository owner is the canonical repository owner
- **AND** it requests enough open pull requests to avoid missing the canonical release-please PR during high-PR-volume periods

#### Scenario: merged beta release already covers main

- **GIVEN** tag `v1.19.0-beta.1` points to `HEAD`
- **AND** release-managed files all contain `1.19.0-beta.1`
- **WHEN** the beta PR sync workflow runs for base version `1.19.0`
- **THEN** it exits without creating `1.19.0-beta.2`

### Requirement: Merged beta release PRs publish GitHub prereleases

When a `release/beta-*` PR merges into `main`, release automation SHALL:

- Require `RELEASE_PLEASE_TOKEN`, with no `GITHUB_TOKEN` fallback.
- Verify all release-managed version files agree on a beta version.
- Create the matching `vX.Y.Z-beta.N` tag at the merge commit and publish its GitHub prerelease.

Reruns after the tag exists SHALL be safe and SHALL NOT create a second tag.

#### Scenario: beta PR merge publishes a prerelease tag

- **GIVEN** a merged pull request from `release/beta-1.19.0-beta.1`
- **AND** release-managed files all contain `1.19.0-beta.1`
- **AND** `RELEASE_PLEASE_TOKEN` is configured
- **WHEN** the beta publish workflow runs
- **THEN** it creates tag `v1.19.0-beta.1` at the merge commit
- **AND** it creates a GitHub prerelease for `v1.19.0-beta.1`

### Requirement: Prerelease artifacts do not advance stable aliases

Release publishing SHALL accept stable (`vX.Y.Z`) and prerelease (`vX.Y.Z-alpha.N`, `vX.Y.Z-beta.N`, `vX.Y.Z-rc.N`) tags. Prereleases SHALL NOT update Docker aliases `latest`, `X`, or `X.Y`. Their GitHub Releases SHALL remain prereleases, not latest. Stable tags SHALL retain existing stable aliases and latest-release behavior.

#### Scenario: beta release publishes beta-only Docker tags

- **GIVEN** release tag `v1.19.0-beta.1`
- **WHEN** the release publishing workflow builds the Docker image
- **THEN** it publishes the exact version tag `1.19.0-beta.1`
- **AND** it MAY publish channel tag `beta`
- **AND** it MUST NOT publish or update `latest`, `1`, or `1.19`

### Requirement: Stable release promotion remains release-please owned

A beta-tested release train SHALL be promoted by merging the normal release-please stable release PR for the corresponding base version. Stable promotion SHALL rebuild PyPI, Docker, Helm, and GitHub Release artifacts with the stable version instead of retagging prerelease artifacts.

#### Scenario: beta train is promoted to stable

- **GIVEN** `v1.19.0-beta.2` was published from `main`
- **AND** release-please has prepared the stable release PR for `1.19.0`
- **WHEN** the stable release PR is merged
- **THEN** release-please creates the stable `v1.19.0` release
- **AND** the release publishing workflow publishes stable artifacts for `1.19.0`
- **AND** stable Docker aliases `latest`, `1`, and `1.19` are updated only by the stable release

