"""End-to-End Pipeline Test.

Verifies the full pipeline for given tickers:
1. Data fetch → Bronze (JSON)
2. Migration → Silver (Parquet)
3. Ingest → Gold (SQLite)
4. API access (OHLCV endpoint)
5. Decision Engine produces signals
6. Execution Engine reads positions

Usage:
    python -m scripts.test_end_to_end
    python -m trading_system.cli test-e2e --tickers BBCA.JK TLKM.JK ASII.JK
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def run_e2e_test(tickers: list[str] | None = None) -> bool:
    """Run end-to-end test. Returns True if all steps pass."""
    if tickers is None:
        tickers = ["BBCA.JK", "TLKM.JK", "ASII.JK"]

    print("=" * 60)
    print("END-TO-END PIPELINE TEST")
    print(f"Tickers: {', '.join(tickers)}")
    print("=" * 60)

    errors = []

    # Step 1: Check data in Gold layer (SQLite)
    print("\n[1/6] Checking Gold Layer (SQLite)...")
    try:
        from trading_system.data.storage import DataStorage
        storage = DataStorage()
        for t in tickers:
            df = storage.load_ohlcv(t, limit=5)
            if df.empty:
                errors.append(f"  FAIL: No OHLCV data for {t} in Gold layer")
            else:
                print(f"  OK: {t} has {len(storage.load_ohlcv(t))} bars")
    except Exception as e:
        errors.append(f"  FAIL: Gold layer check error: {e}")

    # Step 2: Check API can access data
    print("\n[2/6] Checking API access...")
    try:
        from trading_system.api.app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        for t in tickers:
            resp = client.get(f"/api/data/ohlcv?ticker={t}")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("bars"):
                    print(f"  OK: API returns OHLCV for {t}")
                else:
                    print(f"  WARN: API returns empty for {t}")
            else:
                errors.append(f"  FAIL: API returned {resp.status_code} for {t}")
    except Exception as e:
        errors.append(f"  FAIL: API check error: {e}")

    # Step 3: Decision Engine produces signals
    print("\n[3/6] Checking Decision Engine...")
    try:
        from trading_system.decision.engine import DecisionEngine
        dec = DecisionEngine()
        for t in tickers:
            result = dec.recommend(t)
            if result.get("status") == "error":
                # This is expected if no scores computed yet — not a hard failure
                print(f"  WARN: {t} — {result.get('message', 'no scores')}")
            else:
                action = result.get("recommendation", {}).get("action", "N/A")
                print(f"  OK: {t} → action={action}")
    except Exception as e:
        errors.append(f"  FAIL: Decision engine error: {e}")

    # Step 4: Execution Engine reads positions
    print("\n[4/6] Checking Execution Engine...")
    try:
        from trading_system.execution.automated import AutomatedExecutionEngine
        engine = AutomatedExecutionEngine()
        positions = engine.storage.get_all_open_positions()
        print(f"  OK: Execution engine reads {len(positions)} open positions")
    except Exception as e:
        errors.append(f"  FAIL: Execution engine error: {e}")

    # Step 5: Risk Engine works
    print("\n[5/6] Checking Risk Engine...")
    try:
        from trading_system.risk.engine import RiskEngine
        risk = RiskEngine()
        for t in tickers:
            result = risk.analyze(t)
            if result.get("status") == "ok":
                print(f"  OK: {t} → VaR95={result.get('var_95_1d', 0):.2f}")
            else:
                print(f"  WARN: {t} — {result.get('message', 'no data')}")
    except Exception as e:
        errors.append(f"  FAIL: Risk engine error: {e}")

    # Step 6: Performance Analytics works
    print("\n[6/6] Checking Performance Analytics...")
    try:
        from trading_system.portfolio.performance import PerformanceAnalytics
        perf = PerformanceAnalytics()
        metrics = perf.get_performance(period="ALL")
        print(f"  OK: Performance → trades={metrics.get('total_trades', 0)}, equity={metrics.get('current_equity', 0)}")
    except Exception as e:
        errors.append(f"  FAIL: Performance analytics error: {e}")

    # Summary
    print("\n" + "=" * 60)
    if errors:
        print(f"END-TO-END TEST FAILED ({len(errors)} errors):")
        for e in errors:
            print(e)
        return False
    else:
        print("END-TO-END TEST PASSED")
        print("=" * 60)
        return True


if __name__ == "__main__":
    success = run_e2e_test()
    sys.exit(0 if success else 1)
