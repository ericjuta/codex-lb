## Why

The dashboard exposes power-user navigation and settings alongside everyday controls, making the primary operator path harder to scan. This change adapts upstream progressive disclosure while preserving the fork's routes, settings, badges, and eager query behavior.

## What Changes

- Keep Dashboard, Reports, Accounts, APIs, and Settings as primary navigation and move Automations into an Advanced navigation group on desktop and mobile.
- Keep `/automations` directly addressable and preserve the legacy `/firewall` redirect to Settings.
- Keep core Settings sections visible while placing routing, upstream proxy, firewall, quota planner, and sticky-session sections in a collapsed-by-default Advanced group.
- Unmount advanced settings content while collapsed, without deferring the existing eager Accounts and upstream-proxy page queries.
- Preserve fork-specific routes and settings, the Accounts reset-credit badge, and existing route splitting and lazy Recharts boundaries.
- Add English and Simplified Chinese labels plus direct component and integration coverage.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-architecture`: Define primary versus advanced navigation and collapsed advanced-settings behavior while preserving deep links and eager page queries.

## Impact

- Affects dashboard header/navigation, Settings composition, Automations and Firewall integration paths, locale strings, and directly corresponding frontend tests.
- Adds one small reusable Collapsible UI primitive and one Settings composition component.
- Does not change backend APIs, OAuth, database schema, dependencies, routes, or build configuration.
