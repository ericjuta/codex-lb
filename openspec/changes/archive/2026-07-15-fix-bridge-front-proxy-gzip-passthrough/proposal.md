## Why

With the addressable bridge worker pool active (multi-worker runtime), the aiohttp front proxy's client session used aiohttp's default `auto_decompress=True`. Worker responses compressed by the dashboard gzip middleware were transparently gunzipped by the front proxy while the forwarded `Content-Encoding: gzip` header was preserved. Browsers received plaintext bodies labeled as gzip, failed content decoding, and rendered a blank dashboard (assets 200 with undecodable bodies).

## What Changes

- Set `auto_decompress=False` on the bridge front proxy's upstream `aiohttp.ClientSession` so worker response bodies pass through byte-for-byte alongside their original `Content-Encoding` header.
- Add regression coverage that runs a real front proxy against a fake worker serving gzip-encoded assets and asserts the body survives verbatim and decodes.

## Impact

- Affects the multi-worker bridge front proxy response path only; single-worker runtimes are untouched.
- Fixes blank-dashboard loads behind the worker pool (including access via TLS reverse proxies such as `tailscale serve`).
