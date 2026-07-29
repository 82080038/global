#!/usr/bin/env bash
set -e

echo "Stopping old servers..."
pkill -f 'next-server' 2>/dev/null || true
pkill -f 'api/app.py' 2>/dev/null || true
pkill -f 'uvicorn' 2>/dev/null || true
fuser -k 8000/tcp 2>/dev/null || true
sleep 2

echo "Building frontend..."
cd /opt/lampp/htdocs/global/frontend
npm run build

echo "Starting backend..."
cd /opt/lampp/htdocs/global
source venv/bin/activate
nohup venv/bin/python src/trading_system/api/app.py > /tmp/backend.log 2>&1 &

echo "Starting frontend..."
cd /opt/lampp/htdocs/global/frontend
nohup npm start > /tmp/frontend.log 2>&1 &

sleep 5
echo "--- backend ---"
cat /tmp/backend.log
echo "--- frontend ---"
cat /tmp/frontend.log

echo ""
echo "Open: http://127.0.0.1:45469/engines"
