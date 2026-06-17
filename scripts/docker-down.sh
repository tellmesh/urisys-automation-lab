#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMPOSE="${COMPOSE:-docker compose}"
${COMPOSE} -f docker-compose.lab.yml down "$@"
