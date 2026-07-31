@echo off
REM Start all trading system components for production (Windows).
REM Usage: scripts\start_production.bat

echo === Starting Trading System Production ===

REM Activate virtual environment if present
if exist ".venv\Scripts\activate.bat" (
    echo [0/3] Activating .venv ...
    call .venv\Scripts\activate.bat
)

REM Start API server
echo [1/3] Starting API server on :8000 ...
start "Trading API" cmd /k "uvicorn src.trading_system.api.app:app --host 0.0.0.0 --port 8000"

REM Start automated execution engine
echo [2/3] Starting automated execution engine ...
start "Execution Engine" cmd /k "python -m trading_system.cli execution --interval 15"

REM Start daily scheduler
echo [3/3] Starting daily scheduler ...
start "Scheduler" cmd /k "python -m trading_system.cli schedule"

echo.
echo All services started in separate windows.
echo Close the window to stop each service.
pause
