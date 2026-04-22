<!--
About
Codex/ChatGPT account load balancer & proxy with usage tracking, dashboard, and OpenCode-compatible endpoints

Topics
python oauth sqlalchemy dashboard load-balancer openai rate-limit api-proxy codex fastapi usage-tracking chatgpt opencode

Resources
-->

# codex-lb

Load balancer for ChatGPT accounts. Pool multiple accounts, track usage, manage API keys, view everything in a dashboard.

| ![dashboard](docs/screenshots/dashboard.jpg) | ![accounts](docs/screenshots/accounts.jpg) |
|:---:|:---:|

<details>
<summary>More screenshots</summary>

| Settings | Login |
|:---:|:---:|
| ![settings](docs/screenshots/settings.jpg) | ![login](docs/screenshots/login.jpg) |

| Dashboard (dark) | Accounts (dark) | Settings (dark) |
|:---:|:---:|:---:|
| ![dashboard-dark](docs/screenshots/dashboard-dark.jpg) | ![accounts-dark](docs/screenshots/accounts-dark.jpg) | ![settings-dark](docs/screenshots/settings-dark.jpg) |

</details>

## Features

<table>
<tr>
<td><b>Account Pooling</b><br>Load balance across multiple ChatGPT accounts</td>
<td><b>Usage Tracking</b><br>Per-account tokens, cost, 28-day trends</td>
<td><b>API Keys</b><br>Per-key rate limits by token, cost, window, model</td>
</tr>
<tr>
<td><b>Dashboard Auth</b><br>Password + optional TOTP</td>
<td><b>OpenAI-compatible</b><br>Codex CLI, OpenCode, any OpenAI client</td>
<td><b>Auto Model Sync</b><br>Available models fetched from upstream</td>
</tr>
</table>

### Run the Current Checkout in Docker

If you want to run the checked-out repo instead of the published image, or need a direct-container fallback to `docker compose`, use the same `.env.local` config as the `server` service:

```bash
docker build -t codex-lb-server .
docker volume create codex-lb-data
docker run -d --name codex-lb-direct \
  --restart unless-stopped \
  --env-file .env.local \
  -p 127.0.0.1:2455:2455 \
  -p 127.0.0.1:1455:1455 \
  -v codex-lb-data:/var/lib/codex-lb \
  codex-lb-server \
  fastapi run app/main.py --host 0.0.0.0 --port 2455 --reload
```

### Expose It on Tailnet HTTPS with Tailscale

Once the local service is up on `127.0.0.1:2455`, you can publish the same port over tailnet-only HTTPS:

```bash
tailscale serve --bg 2455
tailscale serve status
```

That creates a tailnet HTTPS listener like:

```text
https://<your-node>.<your-tailnet>.ts.net:2455 -> http://127.0.0.1:2455
```

If you need to remove or replace that dedicated `:2455` mapping later:

```bash
tailscale serve clear 2455
```

## Remote Setup

When accessing the dashboard remotely for the first time, a bootstrap token is required to set the initial password.

**Auto-generated (default):** On first startup (no password configured), the server generates a one-time token and prints it to logs:

```bash
docker logs codex-lb
# ============================================
#   Dashboard bootstrap token (first-run):
#   <token>
# ============================================
```

Open the dashboard → enter the token + new password → done. The token is shared across replicas and remains valid until a password is set. In multi-replica setups, replicas must share the same encryption key (the Helm chart default) for restart recovery to work.

**Manual token:** To use a fixed token instead, set the env var before starting:

```bash
docker run -d --name codex-lb \
  -e CODEX_LB_DASHBOARD_BOOTSTRAP_TOKEN=your-secret-token \
  -p 2455:2455 -p 1455:1455 \
  -v codex-lb-data:/var/lib/codex-lb \
  ghcr.io/soju06/codex-lb:latest
```

**Local access** (localhost) bypasses bootstrap entirely — no token needed.

## Client Setup

Point any OpenAI-compatible client at codex-lb. If [API key auth](#api-key-authentication) is enabled, pass a key from the dashboard as a Bearer token.

| Logo | Client | Endpoint | Config |
|---|--------|----------|--------|
| <img src="https://avatars.githubusercontent.com/u/14957082?s=200" width="32" alt="OpenAI"> | **Codex CLI** | `http://127.0.0.1:2455/backend-api/codex` | `~/.codex/config.toml` |
| <img src="https://avatars.githubusercontent.com/u/208539476?s=200" width="32" alt="OpenCode"> | **OpenCode** | `http://127.0.0.1:2455/v1` | `~/.config/opencode/opencode.json` |
| <img src="https://avatars.githubusercontent.com/u/252820863?s=200" width="32" alt="OpenClaw"> | **OpenClaw** | `http://127.0.0.1:2455/v1` | `~/.openclaw/openclaw.json` |
| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/python/python-original.svg" width="32" alt="Python"> | **OpenAI Python SDK** | `http://127.0.0.1:2455/v1` | Code |

<details>
<summary><img src="https://avatars.githubusercontent.com/u/14957082?s=200" width="20" align="center" alt="OpenAI">&ensp;<b>Codex CLI / IDE Extension</b></summary>
<br>

`~/.codex/config.toml`:

```toml
model = "gpt-5.3-codex"
model_reasoning_effort = "xhigh"
model_provider = "codex-lb"

[model_providers.codex-lb]
name = "OpenAI"  # required — enables remote /responses/compact
base_url = "http://127.0.0.1:2455/backend-api/codex"
wire_api = "responses"
supports_websockets = true
requires_openai_auth = true # required for codex app
```

Optional: enable native upstream WebSockets for Codex streaming while keeping `codex-lb` pooling:

```bash
export CODEX_LB_UPSTREAM_STREAM_TRANSPORT=websocket
```

`auto` is the default and uses native WebSockets for native Codex headers or models that prefer them.
You can also switch this in the dashboard under Settings -> Routing -> Upstream stream transport.

Note: Codex itself does not currently expose a stable documented `wire_api = "websocket"` provider mode.
If you want to experiment on the Codex side, the current CLI exposes under-development feature flags:

```toml
[features]
responses_websockets = true
# or
responses_websockets_v2 = true
```

These flags are experimental and do not replace `wire_api = "responses"`.

If upstream websocket handshakes must use environment proxies in your deployment, set
`CODEX_LB_UPSTREAM_WEBSOCKET_TRUST_ENV=true`. By default websocket handshakes connect directly to
match Codex CLI's native transport.

**With [API key auth](#api-key-authentication):**

```toml
[model_providers.codex-lb]
name = "OpenAI"
base_url = "http://127.0.0.1:2455/backend-api/codex"
wire_api = "responses"
env_key = "CODEX_LB_API_KEY"
supports_websockets = true
requires_openai_auth = true # required for codex app
```

```bash
export CODEX_LB_API_KEY="sk-clb-..."   # key from dashboard
codex
```

**Verify WebSocket transport**

Use a one-off debug run:

```bash
RUST_LOG=debug codex exec "Reply with OK only."
```

Healthy websocket signals:

- CLI logs contain `connecting to websocket` and `successfully connected to websocket`
- `codex-lb` logs show `WebSocket /backend-api/codex/responses`
- `codex-lb` logs do **not** show fallback `POST /backend-api/codex/responses` for the same run

If you run `codex-lb` behind a reverse proxy, make sure it forwards WebSocket upgrades.

**Migrating from direct OpenAI** — `codex resume` filters by `model_provider`;
old sessions won't appear until you re-tag them:

```bash
# JSONL session files (all versions)
find ~/.codex/sessions -name '*.jsonl' \
  -exec sed -i '' 's/"model_provider":"openai"/"model_provider":"codex-lb"/g' {} +

# SQLite state DB (>= v0.105.0, creates ~/.codex/state_*.sqlite)
sqlite3 ~/.codex/state_5.sqlite \
  "UPDATE threads SET model_provider = 'codex-lb' WHERE model_provider = 'openai';"
```

</details>

<details>
<summary><img src="https://avatars.githubusercontent.com/u/208539476?s=200" width="20" align="center" alt="OpenCode">&ensp;<b>OpenCode</b></summary>
<br>

> **Important**: Use the built-in `openai` provider with `baseURL` override — not a custom provider with `@ai-sdk/openai-compatible`. Custom providers use the Chat Completions API which **drops reasoning/thinking content**. The built-in `openai` provider uses the Responses API, which properly preserves `encrypted_content` and multi-turn reasoning state.

Before starting, please ensure that all existing OpenAI credentials is cleared in `~/.local/share/opencode/auth.json`
You can clean the config by using this one-liner
`jq 'del(.openai)' ~/.local/share/opencode/auth.json > auth.json.tmp && mv auth.json.tmp ~/.local/share/opencode/auth.json`

`~/.config/opencode/opencode.json`:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "openai": {
      "options": {
        "baseURL": "http://127.0.0.1:2455/v1",
        "apiKey": "{env:CODEX_LB_API_KEY}"
      },
      "models": {
        "gpt-5.4": {
          "name": "GPT-5.4",
          "reasoning": true,
          "options": { "reasoningEffort": "high", "reasoningSummary": "detailed" },
          "limit": { "context": 1050000, "output": 128000 }
        },
        "gpt-5.3-codex": {
          "name": "GPT-5.3 Codex",
          "reasoning": true,
          "options": { "reasoningEffort": "high", "reasoningSummary": "detailed" },
          "limit": { "context": 272000, "output": 65536 }
        },
        "gpt-5.1-codex-mini": {
          "name": "GPT-5.1 Codex Mini",
          "reasoning": true,
          "options": { "reasoningEffort": "high", "reasoningSummary": "detailed" },
          "limit": { "context": 272000, "output": 65536 }
        },
        "gpt-5.3-codex-spark": {
          "name": "GPT-5.3 Codex Spark",
          "reasoning": true,
          "options": { "reasoningEffort": "xhigh", "reasoningSummary": "detailed" },
          "limit": { "context": 128000, "output": 65536 }
        }
      }
    }
  },
  "model": "openai/gpt-5.3-codex"
}
```

This overrides the built-in `openai` provider's endpoint to point at codex-lb while keeping the Responses API code path that handles reasoning properly.

```bash
export CODEX_LB_API_KEY="sk-clb-..."   # key from dashboard
opencode
```

</details>

<details>
<summary><img src="https://avatars.githubusercontent.com/u/252820863?s=200" width="20" align="center" alt="OpenClaw">&ensp;<b>OpenClaw</b></summary>
<br>

`~/.openclaw/openclaw.json`:

```jsonc
{
  "agents": {
    "defaults": {
      "model": { "primary": "codex-lb/gpt-5.4" },
      "models": {
        "codex-lb/gpt-5.4": { "params": { "cacheRetention": "short" } }
        "codex-lb/gpt-5.4-mini": { "params": { "cacheRetention": "short" } }
        "codex-lb/gpt-5.3-codex": { "params": { "cacheRetention": "short" } }
      }
    }
  },
  "models": {
    "mode": "merge",
    "providers": {
      "codex-lb": {
        "baseUrl": "http://127.0.0.1:2455/v1",
        "apiKey": "${CODEX_LB_API_KEY}",   // or "dummy" if API key auth is disabled
        "api": "openai-responses",
        "models": [
          {
            "id": "gpt-5.4",
            "name": "gpt-5.4 (codex-lb)",
            "contextWindow": 1050000,
            "contextTokens": 272000,
            "maxTokens": 4096,
            "input": ["text"],
            "reasoning": false
          },
          {
            "id": "gpt-5.4-mini",
            "name": "gpt-5.4-mini (codex-lb)",
            "contextWindow": 400000,
            "contextTokens": 272000,
            "maxTokens": 4096,
            "input": ["text"],
            "reasoning": false
          },
          {
            "id": "gpt-5.3-codex",
            "name": "gpt-5.3-codex (codex-lb)",
            "contextWindow": 400000,
            "contextTokens": 272000,
            "maxTokens": 4096,
            "input": ["text"],
            "reasoning": false
          }
        ]
      }
    }
  }
}
```

Set the env var or replace `${CODEX_LB_API_KEY}` with a key from the dashboard. If API key auth is disabled,
local requests can omit the key, but non-local requests are still rejected until proxy authentication is configured.

</details>

<details>
<summary><img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/python/python-original.svg" width="20" align="center" alt="Python">&ensp;<b>OpenAI Python SDK</b></summary>
<br>

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:2455/v1",
    api_key="sk-clb-...",  # from dashboard, or any non-empty string if auth is disabled
)

response = client.chat.completions.create(
    model="gpt-5.3-codex",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

</details>

## API Key Authentication

API key auth is **disabled by default**. In that mode, only local requests to the protected proxy routes can
proceed without a key; non-local requests are rejected until proxy authentication is configured. Enable it in
**Settings → API Key Auth** on the dashboard when clients connect remotely or through Docker, VM, or container
networking that appears non-local to the service.

When enabled, clients must pass a valid API key as a Bearer token:

```
Authorization: Bearer sk-clb-...
```

The protected proxy routes covered by this setting are:

- `/v1/*` (except `/v1/usage`, which always requires a valid key)
- `/backend-api/codex/*`
- `/backend-api/transcribe`

**Creating keys**: Dashboard → API Keys → Create. The full key is shown **only once** at creation. Keys support optional expiration, model restrictions, and rate limits (tokens / cost per day / week / month).

## Configuration

Environment variables with `CODEX_LB_` prefix or `.env.local`. See [`.env.example`](.env.example).
SQLite is the default database backend; PostgreSQL is optional via `CODEX_LB_DATABASE_URL` (for example `postgresql+asyncpg://...`).

### Dashboard authentication modes

`codex-lb` supports three dashboard auth modes via environment variables:

- `CODEX_LB_DASHBOARD_AUTH_MODE=standard` — built-in dashboard password with optional TOTP from the Settings page.
- `CODEX_LB_DASHBOARD_AUTH_MODE=trusted_header` — trust a reverse-proxy auth header such as Authelia's `Remote-User`, but only from `CODEX_LB_FIREWALL_TRUSTED_PROXY_CIDRS`. Built-in password/TOTP remain available as an optional fallback, and password/TOTP management still requires a fallback password session.
- `CODEX_LB_DASHBOARD_AUTH_MODE=disabled` — fully bypass dashboard auth. Use only behind network restrictions or external auth. Built-in password/TOTP management is disabled in this mode.

`trusted_header` mode also requires:

```bash
CODEX_LB_FIREWALL_TRUST_PROXY_HEADERS=true
CODEX_LB_FIREWALL_TRUSTED_PROXY_CIDRS=172.18.0.0/16
CODEX_LB_DASHBOARD_AUTH_PROXY_HEADER=Remote-User
```

If the trusted header is missing and no fallback password is configured, the dashboard fails closed and shows a reverse-proxy-required message instead of loading the UI.

### Docker examples

**Authelia / trusted header**

```bash
docker run -d --name codex-lb \
  -p 2455:2455 -p 1455:1455 \
  -e CODEX_LB_DASHBOARD_AUTH_MODE=trusted_header \
  -e CODEX_LB_DASHBOARD_AUTH_PROXY_HEADER=Remote-User \
  -e CODEX_LB_FIREWALL_TRUST_PROXY_HEADERS=true \
  -e CODEX_LB_FIREWALL_TRUSTED_PROXY_CIDRS=172.18.0.0/16 \
  -v codex-lb-data:/var/lib/codex-lb \
  ghcr.io/soju06/codex-lb:latest
```

**Hard override / no app-level dashboard auth**

```bash
docker run -d --name codex-lb \
  -p 2455:2455 -p 1455:1455 \
  -e CODEX_LB_DASHBOARD_AUTH_MODE=disabled \
  -v codex-lb-data:/var/lib/codex-lb \
  ghcr.io/soju06/codex-lb:latest
```

For Helm, pass the same values through `extraEnv`.

## Data

| Environment | Path |
|-------------|------|
| Local / uvx | `~/.codex-lb/` |
| Docker | `/var/lib/codex-lb/` |

Backup this directory to preserve your data.

## Kubernetes

```bash
helm install codex-lb oci://ghcr.io/soju06/charts/codex-lb \
  --set postgresql.auth.password=changeme \
  --set config.databaseMigrateOnStartup=true \
  --set migration.schemaGate.enabled=false
kubectl port-forward svc/codex-lb 2455:2455
```

Open [localhost:2455](http://localhost:2455) → Add account → Done.

The Helm chart auto-configures HTTP `/responses` owner handoff for multi-replica installs using a headless-service DNS name per pod. The default cluster domain is `cluster.local`; set Helm `clusterDomain` if your cluster uses a different suffix. Override `config.sessionBridgeAdvertiseBaseUrl` only if pods must be reached through a different internal address.

For external database, production config, ingress, observability, and more see the [Helm chart README](deploy/helm/codex-lb/README.md).

## Development

```bash
# Docker
docker compose watch

# Local
uv sync && cd frontend && bun install && cd ..
uv run fastapi run app/main.py --reload        # backend :2455
cd frontend && bun run dev                     # frontend :5173
