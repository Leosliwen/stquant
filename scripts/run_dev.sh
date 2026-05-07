#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
exec uvicorn app.main:app --host 0.0.0.0 --port "${STQUANT_PORT:-8501}" --reload
