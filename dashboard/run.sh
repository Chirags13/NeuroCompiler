#!/usr/bin/env bash
# Start the NeuroCompiler dashboard at http://localhost:8000 (local only). Ctrl+C stops it.
cd "$(dirname "$0")/.."
if curl -s -o /dev/null http://127.0.0.1:8000/api/health; then
  echo "Dashboard already running: http://localhost:8000"; exit 0
fi
echo "NeuroCompiler dashboard: http://localhost:8000"
exec .venv/bin/python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8000 --log-level warning
