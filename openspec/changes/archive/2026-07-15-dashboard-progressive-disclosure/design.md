## Context

The fork's dashboard currently renders Automations beside primary navigation and renders every Settings section in one flat stack. Upstream commit `0c2283ee` provides the interaction model, but cannot be transplanted verbatim: this fork has additional routes and settings, an Accounts reset-credit badge, route-level splitting with lazy Recharts, and intentional eager Accounts and upstream-proxy queries on the Settings page.

## Goals / Non-Goals

**Goals:**

- Reduce primary navigation and Settings density through accessible progressive disclosure.
- Preserve every fork-specific route, setting, and account indicator.
- Keep existing page-level Accounts and upstream-proxy queries eager while advanced section components remain unmounted until first expansion.
- Preserve section-owned mutation observers and pending UI state across later collapse and reopen cycles.
- Preserve route splitting, lazy chart loading, and direct deep-link behavior.

**Non-Goals:**

- Adding upstream-only model-source controls.
- Changing APIs, OAuth, backend behavior, migrations, dependencies, build configuration, documentation, or simplicity budgets.
- Changing route paths or moving Accounts/upstream-proxy fetching into the collapsible subtree.

## Decisions

### Separate navigation data into core and advanced groups

The header will keep five core links visible and render Automations in an Advanced dropdown on desktop and a labeled Advanced group in the mobile sheet. Route definitions remain unchanged. This uses the existing Radix dropdown and sheet primitives instead of introducing navigation state or dependencies.

### Use a controlled collapsed-by-default Settings group

A small `AdvancedSettingsGroup` component will own open state and use a reusable Radix Collapsible wrapper. Its children are unmounted until the first expansion, preventing section hooks such as Firewall and Sticky Sessions from running on initial page load. After first expansion, the group keeps its children mounted and only hides the content while closed so in-flight mutation observers and local form state retain their lifecycle.

### Keep page-level query hooks outside the disclosure boundary

`SettingsPage` will continue to call its Accounts and upstream-proxy hooks eagerly at page render. Their resulting data and mutations are passed into advanced child sections only after expansion. This preserves the fork's established prefetch/performance behavior while still deferring section-owned queries.

### Adapt the upstream section set to the fork

Routing, upstream proxy, Firewall, Quota Planner, and Sticky Sessions move into Advanced. Fork-specific core settings remain visible. `ModelSourcesSettings` is omitted because it is upstream-only and absent from this fork.

## Risks / Trade-offs

- [Hidden advanced controls reduce discoverability] -> Provide clear title, description, localized trigger labels, and active-state navigation styling.
- [Retaining mounted content uses resources after first expansion] -> Pay the lifecycle cost only after operator intent is established; preserve observers thereafter to prevent duplicate or conflicting writes.
- [Hidden sections could become keyboard-accessible] -> Use the native `hidden` attribute while closed so retained controls are removed from layout and the accessibility tree.
- [Accidentally deferring eager fork queries] -> Keep hooks at `SettingsPage` scope and assert they run while advanced section mocks remain unmounted.
- [Route or bundle regressions during upstream adaptation] -> Run direct deep-link integration tests, full build, and existing bundle/route checks without changing route modules.
