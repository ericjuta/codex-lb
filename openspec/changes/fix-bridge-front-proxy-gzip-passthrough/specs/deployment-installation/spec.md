## ADDED Requirements

### Requirement: Bridge front proxy preserves worker response encoding

The addressable bridge worker pool front proxy MUST forward worker HTTP response bodies byte-for-byte without transparently decompressing them. When a worker response carries a `Content-Encoding` header, the body the front proxy sends downstream MUST remain the encoded bytes that match that header.

#### Scenario: gzip-encoded dashboard asset passes through verbatim

- **WHEN** a worker responds to an asset request with `Content-Encoding: gzip` and a gzip-compressed body
- **THEN** the front proxy response preserves the `Content-Encoding: gzip` header
- **AND** the response body is the identical compressed bytes, decodable by the client
