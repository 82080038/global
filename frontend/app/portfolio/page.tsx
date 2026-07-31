"use client";

import { useEffect, useState } from "react";
import TerminalLayout from "../components/TerminalLayout";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

interface Position {
  ticker: string;
  quantity: number;
  avg_entry_price: number;
  current_price?: number;
  pnl?: number;
  pnl_pct?: number;
}

interface Exposure {
  cash: number;
  invested: number;
  total_equity: number;
  exposure_pct: number;
  position_count: number;
}

export default function PortfolioPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [exposure, setExposure] = useState<Exposure | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPortfolio = async () => {
    setLoading(true);
    setError(null);
    try {
      const [posRes, expRes] = await Promise.all([
        fetch(`${API_BASE}/api/positions`),
        fetch(`${API_BASE}/api/portfolio/exposure`),
      ]);
      if (posRes.ok) {
        const posData = await posRes.json();
        setPositions(posData.positions || posData || []);
      }
      if (expRes.ok) {
        const expData = await expRes.json();
        setExposure(expData);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load portfolio");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const init = async () => {
      await fetchPortfolio();
    };
    init();
  }, []);

  return (
    <TerminalLayout active="portfolio">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="mb-2 text-lg font-bold text-zinc-100">Portfolio</h1>
          <p className="text-xs text-zinc-500">
            Current positions and portfolio exposure
          </p>
        </div>
        <button
          onClick={fetchPortfolio}
          disabled={loading}
          className="rounded bg-zinc-800 px-4 py-1 text-xs font-bold text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {loading && <div className="text-xs text-zinc-500">Loading...</div>}

      {error && (
        <div className="mb-4 rounded border border-red-800 bg-red-900/30 p-3 text-xs text-red-400">
          {error}
        </div>
      )}

      {exposure && (
        <div className="mb-4 grid grid-cols-5 gap-3">
          <StatCard label="Cash" value={exposure.cash?.toLocaleString("id-ID")} />
          <StatCard label="Invested" value={exposure.invested?.toLocaleString("id-ID")} />
          <StatCard label="Total Equity" value={exposure.total_equity?.toLocaleString("id-ID")} />
          <StatCard label="Exposure" value={`${exposure.exposure_pct}%`} />
          <StatCard label="Positions" value={exposure.position_count} />
        </div>
      )}

      {!loading && positions.length > 0 && (
        <div className="rounded border border-zinc-800 bg-zinc-900/50 p-4">
          <h2 className="mb-2 text-sm font-bold text-zinc-300">Open Positions</h2>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-zinc-500">
                <th className="pb-1 text-left">Ticker</th>
                <th className="pb-1 text-right">Quantity</th>
                <th className="pb-1 text-right">Avg Entry</th>
                <th className="pb-1 text-right">PnL</th>
                <th className="pb-1 text-right">PnL %</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos, i) => (
                <tr key={i} className="text-zinc-400">
                  <td className="py-0.5 font-mono text-zinc-200">{pos.ticker}</td>
                  <td className="py-0.5 text-right">{pos.quantity?.toLocaleString("id-ID")}</td>
                  <td className="py-0.5 text-right">{pos.avg_entry_price?.toLocaleString("id-ID")}</td>
                  <td className={`py-0.5 text-right ${(pos.pnl || 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {pos.pnl?.toLocaleString("id-ID")}
                  </td>
                  <td className={`py-0.5 text-right ${(pos.pnl_pct || 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {pos.pnl_pct?.toFixed(2)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && positions.length === 0 && !error && (
        <div className="text-xs text-zinc-600">No open positions.</div>
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
