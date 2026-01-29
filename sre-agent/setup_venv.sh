#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# You can override python via: PYTHON_BIN=python3.11 ./setup_venv.sh
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[1/4] Using python: $PYTHON_BIN"
$PYTHON_BIN -V

if [[ ! -d ".venv" ]]; then
  echo "[2/4] Creating venv at .venv"
  $PYTHON_BIN -m venv .venv
else
  echo "[2/4] venv already exists at .venv"
fi

echo "[3/4] Installing requirements"
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements.txt

echo "✅ Setup complete."
echo "Activate manually: source .venv/bin/activate"
