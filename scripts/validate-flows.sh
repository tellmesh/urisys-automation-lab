#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PY:-python3}"
FLOWS=(flows/*.uri.flow.yaml)
OUT="${ROOT}/output/expanded"
mkdir -p "$OUT"

echo "== validate YAML syntax =="
for f in "${FLOWS[@]}"; do
  "$PY" -c "import yaml; yaml.safe_load(open('$f'))" && echo "OK $f"
done

if "$PY" -c "import uri2flow" 2>/dev/null; then
  echo "== uri2flow validate + expand =="
  for f in "${FLOWS[@]}"; do
    base=$(basename "$f" .uri.flow.yaml)
    "$PY" -m uri2flow.cli validate "$f"
    "$PY" -m uri2flow.cli expand "$f" --out "$OUT/${base}.uri.graph.yaml"
    echo "OK expand $base"
  done
else
  echo "uri2flow not installed — YAML syntax check only"
fi

echo "PASS validate-flows"
