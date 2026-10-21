## ADDED Requirements

### Requirement: Account sorting by status and remaining quota

The Accounts sort selector SHALL offer ascending and descending ordering by account status and by remaining 5-hour, weekly, and monthly quota percentage. Status order SHALL be active, paused, rate-limited, quota-exceeded, reauthentication-required, then deactivated; descending SHALL reverse this order. Existing sort modes and the default sort mode SHALL retain their behavior.

#### Scenario: Status order

- **WHEN** the operator selects active-first status ordering
- **THEN** active accounts precede paused accounts, which precede rate-limited accounts

#### Scenario: Highest remaining quota

- **WHEN** the operator selects highest remaining quota
- **THEN** known values appear in descending order and missing values remain last

### Requirement: Quota sort treats missing values as unknown and keeps ties deterministic

Missing quota values SHALL sort after known values in both directions, and zero SHALL be treated as a known value. Ties SHALL use the existing deterministic reset-time, name, and account-ID order. The selected ordering SHALL apply before filtering and SHALL remain selected while the search or status filter changes.

#### Scenario: Lowest remaining monthly quota

- **WHEN** the operator selects lowest remaining monthly quota
- **THEN** an account at zero percent appears before one at 80 percent
- **AND** an account with unknown monthly quota appears after both

#### Scenario: Selection survives filtering

- **WHEN** the operator selects a quota sort mode and then types a search filter
- **THEN** the selected mode remains active and the filtered rows keep that order
