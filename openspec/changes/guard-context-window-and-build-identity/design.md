# Design

## Context guard

Use the normalized Responses payload and model registry metadata after model
and API-key policy normalization. Estimate serialized wire tokens at four
characters per token and reserve ten percent of the effective context window
as headroom. Reject only when the estimate is available and reaches that
guard limit. Prior-response and conversation anchors, plus opaque file/image
references, make the full upstream context unknowable and therefore skip the
local estimate.

The rejection is a 400 OpenAI error with code 'context_length_exceeded' and a
bounded message. It is emitted before admission, reservation, account selection,
or upstream connection. WebSocket requests use the existing error-event envelope.

## Build identity

The Dockerfile accepts 'CODEX_LB_GIT_SHA', stores it in
'CODEX_LB_BUILD_SHA', and writes it to
'org.opencontainers.image.revision'. 'update.sh' and Makefile Docker targets
derive the value from the checked-out commit. The existing application-version
middleware adds 'X-App-Build-SHA' when the response is successful or
client-error; 'unknown' is used for builds that do not provide a SHA.
