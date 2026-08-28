## 1. Implementation

- [x] 1.1 Classify protected agent-control call IDs by exact namespace and
      `function_call` or `custom_tool_call` type in the reusable proxy
      slimming logic.
- [x] 1.2 Apply that classification in both the bridge/service and direct
      WebSocket historical slimming loops.
- [x] 1.3 Classify IDs from the original request before outbound serialization,
      while retaining replay namespaces in this fork's wire payload.
- [x] 1.4 Restrict pre-normalization classification to the historical prefix so
      recent calls cannot protect historical outputs with reused IDs.
- [x] 1.5 Pair each output with its nearest preceding unmatched same-protocol
      call so a namespaced call cannot protect an ordinary same-protocol
      output that reuses its call ID, and an orphan output cannot consume a
      later namespaced call's pairing.

## 2. Regression coverage

- [x] 2.1 Prove both live slim paths retain a namespaced agent wait output
      while slimming an unrelated shell output and an unnamespaced bare-name
      user tool.
- [x] 2.2 Prove HTTP and WebSocket bridge forwarding preserves both namespaced
      function and custom outputs while retaining replay namespaces, and prove the
      WebSocket fresh-resend payload uses the same slimming decision.
- [x] 2.3 Prove a recent namespaced call does not protect a historical output
      that reuses its call ID.
- [x] 2.4 Prove two pending same-protocol calls sharing one call ID pair outputs to the
      nearest unmatched call in LIFO order through live bridge forwarding.
- [x] 2.5 Prove an orphan historical output whose call was trimmed from
      replay is still slimmed while a later namespaced pair reusing the same
      call ID keeps its output, at a live bridge boundary.

## 3. Validation

- [ ] 3.1 Run the focused agent-control-output tests, `make lint`, and
      `make typecheck`.
