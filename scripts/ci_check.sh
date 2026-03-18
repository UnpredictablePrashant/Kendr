#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export OPENAI_API_KEY="${OPENAI_API_KEY:-test-openai-key}"
export PYTHONPATH="${PYTHONPATH:-.}"

echo "[ci] compileall"
python3 -m compileall app.py gateway_server.py setup_ui.py superagent tasks mcp_servers

echo "[ci] unit tests"
python3 -m unittest discover -s tests -v

echo "[ci] docker build"
docker build -t superagent-ci-check .

echo "[ci] ok"
