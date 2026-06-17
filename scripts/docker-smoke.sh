#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAB_PORT="${URISYS_LAB_PORT:-8099}"
RDP_PORT="${URISYS_RDP_PORT:-8795}"

curl -fsS "http://127.0.0.1:${LAB_PORT}/health" | python3 -m json.tool
curl -fsS "http://127.0.0.1:${RDP_PORT}/health" | python3 -m json.tool

curl -fsS -X POST "http://127.0.0.1:${LAB_PORT}/uri/call" \
  -H 'Content-Type: application/json' \
  -d '{"uri":"stt://local/session/main/query/transcript","payload":{"text":"kliknij OK"},"context":{"approved":true}}' \
  | python3 -m json.tool

curl -fsS -X POST "http://127.0.0.1:${LAB_PORT}/uri/call" \
  -H 'Content-Type: application/json' \
  -d '{"uri":"chat://local/uri/command/execute","payload":{"transcript":"kliknij OK","dry_run":true,"approved":true},"context":{"approved":true,"dry_run":true}}' \
  | python3 -m json.tool

echo "PASS docker smoke"
