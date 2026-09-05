## ADDED Requirements

### Requirement: Owner forwarding rejects illegal reconstructed header metadata

Owner-forwarded HTTP bridge requests MUST validate reconstructed bridge metadata
before building signatures or posting headers to another owner. Metadata values
that become signed bridge headers MUST NOT contain control characters below
U+0020 other than horizontal tab, or U+007F. Header names MUST NOT contain any
such control character, including horizontal tab. If original affinity,
downstream turn-state, client-IP, origin or target instance, or reservation
metadata is unsafe, the proxy MUST fail closed with the structured
`bridge_forward_invalid` error and MUST NOT dispatch the owner request. Ordinary
client headers with unsafe names or values MUST be omitted from the forwarded
header map. File-affinity and continuity-owner selection MUST remain unchanged.

#### Scenario: Unsafe reservation metadata fails closed

- **GIVEN** an owner-forward request carries API-key reservation metadata
- **AND** one reservation field contains an illegal HTTP header control character
- **WHEN** the origin builds the owner-forward request
- **THEN** it returns `bridge_forward_invalid`
- **AND** it does not post to the owner or silently omit only the reservation metadata

#### Scenario: Unsafe client header is omitted

- **GIVEN** an owner-forward request includes ordinary client headers with unsafe names or values
- **WHEN** the origin builds the owner-forward request
- **THEN** those client headers are not forwarded
- **AND** safe header values containing horizontal tab remain forwardable
- **AND** the signed bridge-forward metadata remains valid
