#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}/packages/python:${ROOT}/../urirdp-docker/packages/python:${PYTHONPATH:-}"
export URISYS_RDP_URL="${URISYS_RDP_URL:-http://127.0.0.1:8795}"

bash scripts/validate-flows.sh

echo "Starting lab server on http://127.0.0.1:8099"
echo "Ensure urirdp-docker is up on :8795 for KVM/RDP real calls."
exec python3 server/automation_lab_server.py
