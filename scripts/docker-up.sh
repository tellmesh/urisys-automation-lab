#!/usr/bin/env bash
# Start full lab stack: urirdp (:8795, :3389) + automation-lab UI (:8099)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE="${COMPOSE:-docker compose}"
FILE="${ROOT}/docker-compose.lab.yml"

if [[ ! -f "../.env" ]]; then
  echo "hint: create urisys/.env for OPENROUTER_API_KEY / LLM_MODEL (optional for mock dry-run)" >&2
fi

${COMPOSE} -f "$FILE" up --build -d "$@"
echo
echo "urisys automation lab"
echo "  UI:   http://127.0.0.1:${URISYS_LAB_PORT:-8099}"
echo "  URI:  http://127.0.0.1:${URISYS_RDP_PORT:-8795}/uri/call"
echo "  RDP:  127.0.0.1:${RDP_PORT:-3389}  user=${RDP_USER:-urisys}"
echo
${COMPOSE} -f "$FILE" ps
