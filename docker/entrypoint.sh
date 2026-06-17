#!/usr/bin/env bash
set -euo pipefail

mkdir -p /opt/lab/data
echo "automation-lab waiting for urirdp at ${URISYS_RDP_URL:-http://urirdp:8795}"

for i in $(seq 1 60); do
  if curl -fsS "${URISYS_RDP_URL:-http://urirdp:8795}/health" >/dev/null 2>&1; then
    echo "urirdp is healthy"
    break
  fi
  if [[ "$i" -eq 60 ]]; then
    echo "warning: urirdp not healthy after 60 attempts — starting lab anyway" >&2
  fi
  sleep 2
done

exec "$@"
