## Why

The planner settings update request accepts impossible clock times such as `24:00`
or `99:99` because its only check is two digits, a colon, and two digits. The
scheduler then falls back to default working hours, so the saved setting does not
describe its behavior.

## What Changes

- Reject supplied `workingHoursStart` / `workingHoursEnd` values that are not
  ASCII 24-hour `HH:MM` from `00:00` through `23:59`.
- Use the existing HTTP 400 `invalid_quota_planner` envelope, validated before
  persistence, like timezone and working-day validation.
- Keep omitted and null times retaining the stored value, and keep legacy rows
  readable.

## Impact

- Affected spec: `quota-phase-planner`.
- Affected code: quota planner settings update API and request schema.
