## ADDED Requirements

### Requirement: Docker runtime publishes the deployed Git identity

When 'CODEX_LB_GIT_SHA' is provided as a build argument, the image MUST expose
that value as the 'org.opencontainers.image.revision' label and as the
'CODEX_LB_BUILD_SHA' runtime environment value. HTTP responses with status below
500 MUST include the same value in 'X-App-Build-SHA'. Builds without an explicit
SHA MUST use the literal value 'unknown'.

#### Scenario: Direct deployment exposes the checkout SHA

- **WHEN** the direct Docker helper builds the current checkout
- **THEN** it passes the checkout Git SHA to the image build
- **AND** the running health endpoint exposes that SHA in 'X-App-Build-SHA'
