#!/usr/bin/env bash
# Start all trading system components for production.
# Usage: bash scripts/start_production.sh

set -e

echo "=== Starting Trading System Production ==="

# Activate virtual environment if present
if [ -f ".venv/bin/activate" ]; then
    echo "[0/3] Activating .venv ..."
    source .venv/bin/activate
fi

# Start API server
echo "[1/3] Starting API server on :8000 ..."
uvicorn src.trading_system.api.app:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Start automated execution engine
echo "[2/3] Starting automated execution engine ..."
python -m trading_system.cli execution --interval 15 &
EXEC_PID=$!

# Start daily scheduler
echo "[3/3] Starting daily scheduler ..."
python -m trading_system.cli schedule &
SCHED_PID=$!

echo ""
echo "All services started:"
echo "  API:        http://localhost:8000 (PID $API_PID)"
echo "  Execution:  PID $EXEC_PID"
echo "  Scheduler:  PID $SCHED_PID"
echo ""
echo "Press Ctrl+C to stop all services."

trap "kill $API_PID $EXEC_PID $SCHED_PID 2>/dev/null; exit" INT TERM

wait
