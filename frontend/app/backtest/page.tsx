"use client";

import { useState } from "react";
import TerminalLayout from "../components/TerminalLayout";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

interface BacktestResult {
  ticker: string;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
  equity_curve: { date: string; equity: number }[];
}

export default function BacktestPage() {
  const [ticker, setTicker] = useState("BBCA.JK");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runBacktest = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/backtest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, strategy: "buy_and_hold" }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <TerminalLayout active="backtest" ticker={ticker}>
      <div className="mb-4">
        <h1 className="mb-2 text-lg font-bold text-zinc-100">Backtest</h1>
        <p className="text-xs text-zinc-500">
          Run historical strategy backtest for a ticker
        </p>
      </div>

      <div className="mb-4 flex gap-2">
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          placeholder="e.g. BBCA.JK"
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-100"
        />
        <button
          onClick={runBacktest}
          disabled={loading}
          className="rounded bg-blue-600 px-4 py-1 text-xs font-bold text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {loading ? "Running..." : "Run Backtest"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-800 bg-red-900/30 p-3 text-xs text-red-400">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-5 gap-3">
            <StatCard label="Total Return" value={`${result.total_return?.toFixed(2)}%`} />
            <StatCard label="Sharpe Ratio" value={result.sharpe_ratio?.toFixed(2)} />
            <StatCard label="Max Drawdown" value={`${result.max_drawdown?.toFixed(2)}%`} />
            <StatCard label="Win Rate" value={`${result.win_rate?.toFixed(1)}%`} />
            <StatCard label="Total Trades" value={result.total_trades} />
          </div>

          {result.equity_curve && result.equity_curve.length > 0 && (
            <div className="rounded border border-zinc-800 bg-zinc-900/50 p-4">
              <h2 className="mb-2 text-sm font-bold text-zinc-300">Equity Curve</h2>
              <div className="h-64 overflow-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-zinc-500">
                      <th className="pb-1 text-left">Date</th>
                      <th className="pb-1 text-right">Equity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.equity_curve.slice(-20).map((row, i) => (
                      <tr key={i} className="text-zinc-400">
                        <td className="py-0.5">{row.date}</td>
                        <td className="py-0.5 text-right">
                          {row.equity?.toLocaleString("id-ID")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {!result && !loading && !error && (
        <div className="text-xs text-zinc-600">
          Enter a ticker and click Run Backtest to see results.
        </div>
      )}
    </TerminalLayout>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="mt-1 text-sm font-bold text-zinc-100">{value}</div>
    </div>
  );
}
