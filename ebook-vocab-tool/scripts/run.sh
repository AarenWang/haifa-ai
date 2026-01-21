#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "❌ .venv not found. Run: ./scripts/setup_venv.sh"
  exit 1
fi

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  source .venv/bin/activate
fi
export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
python -m ebook_vocab.cli "$@"
