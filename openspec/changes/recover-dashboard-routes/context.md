# Dashboard route recovery context

## Purpose

Keep shell context and native recovery controls visible when a dashboard route
is unknown, pending, or fails to load.

## Decision

The wildcard route remains under `AppLayout`. A pathname-keyed React error
boundary surrounds only the lazy outlet and tracks the complete React Router
location as a reset identity. Location changes reset only an already-failed
boundary, so healthy query/hash updates preserve outlet state and focus.
Pending chunks use the existing SpinnerBlock. Rejected lazy imports use full
reload because React caches the rejected promise; Dashboard navigation creates
a new router location identity even when its URL is unchanged.

## Constraints

- Preserve route-level code splitting and shell landmarks.
- No dependency, global error system, API change, or navigation item.
- No fixed sleeps or polling in tests.
- Reuse existing Button, SpinnerBlock, icons, and semantic tokens.

## Upstream Evidence

- Upstream commit: 628b62061c54e5ac53ee15f10f21519113491d23 (#2018)
- RED: unknown route had no recovery surface; Accounts render failure escaped to the React root
- GREEN: both focused integration cases pass with shell landmarks, heading focus, keyboard actions, and recovery removal
- Route/dashboard integration controls: 31 passed in upstream verification run

## Example

If the Accounts chunk is unavailable, `/accounts` keeps header/main/status,
announces a route-load error, and offers reload or Dashboard. An unknown
bookmark shows Not Found inside the same shell.
