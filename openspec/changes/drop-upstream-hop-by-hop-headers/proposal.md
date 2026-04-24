# Change Proposal: Drop upstream hop-by-hop headers

## Problem

Remote compact requests can arrive with HTTP framing headers such as `Transfer-Encoding: chunked`. `codex-lb` parses and reserializes the JSON body before calling upstream, but it currently forwards some downstream framing headers unchanged. ChatGPT's Cloudflare edge rejects the resulting upstream compact request with an HTML `400 Bad Request` before the compact endpoint can handle it.

## Scope

- Strip downstream hop-by-hop, body-framing, and proxy-loop headers before upstream Responses forwarding.
- Keep proxy-generated upstream `Accept`, `Content-Type`, auth, account, and request-id headers as the source of truth.
- Apply the shared header policy to streaming, compact, and transcribe paths that already use `filter_inbound_headers()`.

## Non-Goals

- Change compact response semantics or add a surrogate compact fallback.
- Change reverse-proxy or Cloudflare configuration.
