#!/usr/bin/env bash
set -euo pipefail

container_name="${CODEX_LB_CONTAINER_NAME:-codex-lb-direct}"
image_name="${CODEX_LB_IMAGE_NAME:-codex-lb-server}"
volume_name="${CODEX_LB_VOLUME_NAME:-codex-lb-data}"
bridge_safe_workers="${CODEX_LB_DIRECT_UVICORN_WORKERS:-1}"

docker build -t "${image_name}" .
docker volume create "${volume_name}" >/dev/null
docker rm -f "${container_name}" >/dev/null 2>&1 || true
docker run -d --name "${container_name}" \
  --restart unless-stopped \
  --env-file .env.local \
  -e CODEX_LB_UVICORN_WORKERS="${bridge_safe_workers}" \
  -p 127.0.0.1:2455:2455 \
  -p 127.0.0.1:1455:1455 \
  -v "${volume_name}":/var/lib/codex-lb \
  "${image_name}"
