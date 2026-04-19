#!/usr/bin/env bash
set -euo pipefail

git pull
docker stop codex-lb
docker rm codex-lb
docker build -t codex-lb-server .
docker run -d --name codex-lb --env-file .env.local -p 127.0.0.1:2455:2455 -p 127.0.0.1:1455:1455 -v codex-lb-data:/var/lib/codex-lb --restart unless-stopped codex-lb-server:latest
