#!/bin/bash
# Menjalankan seluruh simulasi trading system
# Jalankan: bash scripts/run_simulations.sh

set -e
cd "$(dirname "$0")/.."  # auto-detect project root

echo "============================================================"
echo "  TRADING SYSTEM - SIMULASI LENGKAP"
echo "============================================================"
echo ""

# 1. Paper Trade
echo "============================================================"
echo "  1. PAPER TRADE - UNVR.JK"
echo "============================================================"
./venv/bin/python -m trading_system.cli paper-trade UNVR.JK
echo ""
read -p "Tekan Enter untuk lanjut ke Backtest..."

# 2. Backtest
echo "============================================================"
echo "  2. BACKTEST - BBCA.JK (Buy & Hold)"
echo "============================================================"
./venv/bin/python -m trading_system.cli backtest BBCA.JK --strategy buy_and_hold
echo ""
read -p "Tekan Enter untuk lanjut ke Monte Carlo..."

# 3. Monte Carlo
echo "============================================================"
echo "  3. MONTE CARLO SIMULATION - BBCA.JK (1000 runs)"
echo "============================================================"
./venv/bin/python -m trading_system.cli backtest BBCA.JK --strategy buy_and_hold --monte-carlo --n-simulations 1000
echo ""
read -p "Tekan Enter untuk lanjut ke Walk-Forward..."

# 4. Walk-Forward
echo "============================================================"
echo "  4. WALK-FORWARD ANALYSIS - BBCA.JK (MA Crossover)"
echo "============================================================"
./venv/bin/python -m trading_system.cli backtest BBCA.JK --strategy ma_crossover --walk-forward --n-splits 5
echo ""

echo "============================================================"
echo "  SIMULASI SELESAI"
echo "============================================================"
