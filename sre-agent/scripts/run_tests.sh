#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

UNIT_DIR="$ROOT_DIR/tests/unit"
INTEGRATION_DIR="$ROOT_DIR/tests/integration"

case "${1:-}" in
  unit)
    python -m unittest discover -s "$UNIT_DIR" -p "test_*.py"
    ;;
  e2e)
    python "$INTEGRATION_DIR/e2e_local_exec.py"
    ;;
  pytest)
    pytest -q "$ROOT_DIR/tests"
    ;;
  *)
    echo "Usage: $0 {unit|e2e|pytest}"
    exit 1
    ;;
esac
