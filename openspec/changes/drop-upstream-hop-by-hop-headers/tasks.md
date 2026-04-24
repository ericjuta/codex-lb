## 1. Implementation

- [x] 1.1 Drop downstream hop-by-hop and body-framing headers in the shared upstream header filter.
- [x] 1.2 Drop `Connection`-nominated extension headers.

## 2. Verification

- [x] 2.1 Add unit coverage for stripped framing/proxy-loop headers.
- [x] 2.2 Add compact integration coverage for stripped upstream headers.
- [x] 2.3 Run targeted tests and OpenSpec validation.
