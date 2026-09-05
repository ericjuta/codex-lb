# Forward hard continuity retained on canonical prompt-cache bridges

## Why

An HTTP Responses bridge can begin with a soft prompt-cache key and later
publish a turn-state or previous-response alias. Durable lookup intentionally
preserves the original prompt-cache key as the canonical bridge identity. When
a continuation lands on another replica, classifying ownership only from that
canonical key's soft strength can attempt a local rebind, lose the live owner's
durable claim, and return `bridge_instance_mismatch` instead of using the
existing authenticated owner-forward transport.

## What Changes

- Treat an incoming turn-state or previous-response reference as hard bridge
  continuity when choosing between remote-owner forwarding and soft local
  prompt-cache rebinding, even when durable lookup retains a canonical
  prompt-cache key.
- Preserve prompt-cache-only requests as soft locality and preserve the existing
  explicit recovery-rebind exceptions.
- Release local inflight creation ownership when the request is handed to a
  remote owner.
- Preserve the fork's separate file-owner and continuity-owner decisions; this
  change does not alter file affinity or account selection.
- Add service-level and `/v1/responses` regression coverage for the cross-replica
  continuation path.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `sticky-session-operations`: hard continuation evidence overrides the soft
  strength of a retained canonical prompt-cache bridge for replica ownership.

## Impact

- Affected code: HTTP bridge remote-owner selection in
  `app/modules/proxy/_service/http_bridge/mixin.py`.
- Affected behavior: a continuation received by a non-owner replica is forwarded
  internally rather than failing after a local durable claim.
- No setting, schema migration, load-balancer API, endpoint, dashboard, or file
  ownership change is introduced.
