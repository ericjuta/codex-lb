## ADDED Requirements

### Requirement: Dashboard navigation progressively discloses advanced destinations
The dashboard header SHALL present Dashboard, Reports, Accounts, APIs, and Settings as primary navigation destinations and SHALL place Automations in an Advanced navigation group on desktop and mobile. Existing route paths and direct deep links MUST remain unchanged.

#### Scenario: Open Automations from desktop navigation
- **WHEN** an operator opens the desktop Advanced navigation menu and selects Automations
- **THEN** the dashboard navigates to `/automations`
- **AND** the Automations page renders without a full-page reload

#### Scenario: Open Automations directly
- **WHEN** an operator loads `/automations` directly
- **THEN** the Automations page renders successfully
- **AND** the Advanced navigation control indicates that an advanced destination is active

#### Scenario: Find Automations in mobile navigation
- **WHEN** an operator opens the mobile navigation sheet
- **THEN** Automations is listed under an Advanced group label

### Requirement: Settings page progressively discloses advanced sections
The Settings page SHALL keep core settings visible and SHALL place routing, upstream proxy, Firewall, Quota Planner, and Sticky Sessions in one collapsed-by-default Advanced settings group. Advanced section components MUST remain unmounted until the first expand interaction. After first expansion, the components MUST remain mounted but hidden while collapsed so section-owned mutation observers and pending controls retain their lifecycle.

#### Scenario: View core settings before expansion
- **WHEN** an operator opens Settings without interacting with the Advanced settings group
- **THEN** core appearance, import, authentication, API-key, and fork-specific settings remain visible
- **AND** routing, upstream proxy, Firewall, Quota Planner, and Sticky Sessions sections are not mounted

#### Scenario: Expand advanced settings
- **WHEN** an operator activates the Show advanced settings control
- **THEN** routing, upstream proxy, Firewall, Quota Planner, and Sticky Sessions sections render
- **AND** the control exposes a localized Hide advanced settings label

#### Scenario: Preserve an in-flight advanced mutation across collapse
- **WHEN** an advanced section mutation is pending after the operator has expanded the group
- **AND** the operator collapses and reopens the group before that mutation settles
- **THEN** the section's mutation observer remains mounted
- **AND** the corresponding pending control remains disabled or busy
- **AND** the interface does not permit a duplicate or conflicting write from remounting into an idle state

#### Scenario: Preserve eager Settings page queries
- **WHEN** an operator opens Settings while the Advanced settings group remains collapsed
- **THEN** the existing Accounts and upstream-proxy page queries start eagerly
- **AND** section-owned advanced queries do not start until their sections first mount

### Requirement: Progressive disclosure preserves fork dashboard behavior
The progressive-disclosure composition MUST preserve fork-specific routes, settings, Accounts reset-credit indicators, route splitting, lazy Recharts loading, and legacy Firewall routing behavior.

#### Scenario: Open legacy Firewall route
- **WHEN** an operator loads `/firewall`
- **THEN** the dashboard redirects to `/settings`
- **AND** the Settings page presents the collapsed Advanced settings control

#### Scenario: Preserve fork-specific dashboard surfaces
- **WHEN** the progressive-disclosure change is built and tested
- **THEN** existing fork-specific routes and settings remain available
- **AND** the Accounts reset-credit badge remains rendered by the Accounts surface
- **AND** existing route-level and Recharts lazy-loading boundaries remain intact
