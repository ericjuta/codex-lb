## ADDED Requirements

### Requirement: Quota planner timezone settings are validated before persistence

The quota planner settings update API MUST trim a supplied timezone value. A missing, null, empty, or whitespace-only timezone MUST retain the currently stored timezone. A nonblank trimmed value MUST resolve as an IANA timezone name through the installed timezone database; otherwise the API MUST reject the request with HTTP 400 and error code `invalid_quota_planner` before persisting any supplied setting.

#### Scenario: Malformed or unknown timezone is rejected without saving

- **GIVEN** quota planner settings are stored
- **WHEN** a dashboard user updates settings with timezone `/Europe/Stockholm`,
  `Europe/Stockholm/`, `Europe/../Stockholm`, or `Unknown/Timezone` together
  with other setting changes
- **THEN** the API responds with HTTP 400 and error code `invalid_quota_planner`
- **AND** subsequently reading settings returns the previously stored values
  for every field

#### Scenario: Valid timezone is trimmed

- **WHEN** a dashboard user updates settings with timezone ` Europe/Stockholm `
- **THEN** the stored and returned timezone is `Europe/Stockholm`

#### Scenario: Blank timezone retains the current value

- **GIVEN** a timezone is stored, including a legacy invalid value
- **WHEN** a dashboard user updates other settings with the timezone omitted,
  null, empty, or whitespace-only
- **THEN** the other settings are saved
- **AND** the stored timezone is unchanged

### Requirement: Legacy invalid planner timezones fall back to UTC

The planner MUST interpret planner-local times in UTC instead of raising an error during routing-cost or forecast calculation when a stored quota planner timezone is an unknown name or a malformed key. The stored value MUST NOT be rewritten by this fallback.

#### Scenario: Routing costs tolerate a malformed stored timezone

- **GIVEN** planner settings store timezone `/Europe/Stockholm` or
  `Europe/Stockholm/`
- **WHEN** routing costs are built for a cold account with a short usage window
- **THEN** the costs equal those computed with timezone `UTC`

#### Scenario: Forecast tolerates a malformed stored timezone

- **GIVEN** planner settings store a malformed timezone key
- **WHEN** a dashboard user requests the quota planner forecast
- **THEN** the API responds successfully
- **AND** the stored timezone remains unchanged
