## ADDED Requirements

### Requirement: Image routes select a code-owned Responses host model

The system SHALL select the internal Responses host for both
`POST /v1/images/generations` and `POST /v1/images/edits` from the ordered
candidates `gpt-5.6-luna`, then `gpt-5.5`. A candidate SHALL qualify only when
the existing model registry reports non-empty plan visibility and does not mark
that candidate suppressed. If neither candidate qualifies, the system SHALL
select `gpt-5.6-luna` as the default host.

The system MUST NOT expose an `images_host_model` setting or use operator
configuration to override this selection. The system MUST preserve
`images_default_model` and the public `gpt-image-2` default. Host selection MUST
NOT change public image-model policy, accounting, or request-log identity.
Catalog visibility MUST NOT grant account entitlement or bypass existing
account routing, authentication, suppression, or retry behavior.

#### Scenario: Both image routes prefer visible Luna over the old host

- **GIVEN** the registry reports non-empty plan visibility for both candidates and neither is suppressed
- **AND** the upstream accepts image requests hosted by Luna but rejects those hosted by `gpt-5.5`
- **WHEN** a client submits a valid generation request or multipart edit with public model `gpt-image-2`
- **THEN** the internal Responses model is `gpt-5.6-luna`
- **AND** the client receives the successful public image response without exposing the host model

#### Scenario: Hidden Luna falls back to visible GPT-5.5

- **GIVEN** Luna has no registry plan visibility and `gpt-5.5` has non-empty plan visibility without suppression
- **WHEN** a client submits a valid image generation or edit request
- **THEN** the internal Responses host is `gpt-5.5`

#### Scenario: Suppressed Luna is not selected ahead of visible GPT-5.5

- **GIVEN** Luna is suppressed, even if it has registry plan visibility
- **AND** `gpt-5.5` has non-empty plan visibility without suppression
- **WHEN** a client submits a valid image generation or edit request
- **THEN** the internal Responses host is `gpt-5.5`

#### Scenario: Neither candidate qualifies

- **GIVEN** neither candidate has non-empty registry plan visibility without suppression
- **WHEN** a client submits a valid image generation or edit request
- **THEN** the internal Responses host defaults to `gpt-5.6-luna`
- **AND** existing account routing still determines whether any account can serve that host

#### Scenario: Public model identity remains independent of the host

- **WHEN** a valid image generation or edit request omits its public model
- **THEN** it uses the unchanged `images_default_model` setting, whose default is `gpt-image-2`
- **AND** the image tool configuration, API-key policy, accounting, and request logs use the effective public image model rather than the selected Responses host
