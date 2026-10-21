# Context

## Purpose

Stop the planner settings API from saving working hours that are not real clock times.

## Upstream provenance

Narrow port of upstream `6ed4c44fd` (#2540). Upstream validates in the Pydantic update request and
returns HTTP 422. The fork instead validates in the settings API beside timezone and working-day
validation, so the response is the fork's existing HTTP 400 `invalid_quota_planner` envelope and the
check runs before `upsert_settings`, cache invalidation, and audit logging. Upstream's spec and test cases
are otherwise adopted.

## Decisions

- The update request schema no longer carries a digit pattern. One API-level check avoids two
  different statuses for different bad inputs (a schema pattern would return 422 for some values
  and the API check 400 for others, such as non-ASCII digits).
- The response schema keeps its lenient `\d{2}:\d{2}` pattern so legacy rows stay readable.
- The scheduler's fallback for malformed stored times is unchanged.

## Failure modes

- A client that sent an out-of-range time previously got HTTP 200 and silently ran on default hours;
  it now gets HTTP 400 and must correct the value.

## Example

`PUT /api/quota-planner/settings {"workingHoursStart": "24:00", "maxWarmupsPerDay": 99}` returns HTTP 400
`invalid_quota_planner`; `maxWarmupsPerDay` is not saved. `{"workingHoursStart": "00:00", "workingHoursEnd": "23:59"}` is accepted.
