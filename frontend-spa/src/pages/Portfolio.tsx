import { useCallback, useEffect, useState } from "react";
import { apiFetch, safeApiFetch } from "../lib/api";

interface Position {
  ticker: string;
  shares: number;
  avg_price: number;
  current_price?: number;
  market_value?: number;
  unrealized_pnl?: number;
  unrealized_pnl_pct?: number;
  stop_loss?: number;
  take_profit?: number;
  trailing_stop_pct?: number;
  status?: string;
}

interface Exposure {
  cash: number;
  invested: number;
  total_equity: number;
  exposure_pct: number;
  position_count: number;
}

interface Performance {
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
  current_equity: number;
  initial_capital: number;
  equity_curve: { date: string; equity: number }[];
}

interface Order {
  id?: number;
  ticker?: string;
  side?: string;
  shares?: number;
  price?: number;
  status?: string;
  timestamp?: string;
  [k: string]: unknown;
}

interface RebalanceStatus {
  enabled: boolean;
  frequency: string;
  target_weights: Record<string, number>;
  current_weights: Record<string, number>;
  total_portfolio_value: number;
  drift: Record<string, number>;
}

export default function Portfolio() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [exposure, setExposure] = useState<Exposure | null>(null);
  const [performance, setPerformance] = useState<Performance | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [rebalance, setRebalance] = useState<RebalanceStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [orderLimit, setOrderLimit] = useState(20);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [posRes, expRes, perfRes, ordRes, rebRes] = await Promise.all([
        apiFetch("/api/positions"),
        apiFetch("/api/portfolio/exposure"),
        apiFetch("/api/performance"),
        apiFetch(`/api/orders?limit=${orderLimit}`),
        safeApiFetch<RebalanceStatus>("/api/rebalance/status"),
      ]);
      const posJson = await posRes.json();
      const expJson = await expRes.json();
      const perfJson = await perfRes.json();
      const ordJson = await ordRes.json();
      setPositions(posJson.positions || []);
      setExposure(expJson);
      setPerformance(perfJson);
      setOrders(ordJson.orders || []);
      if (rebRes.data) setRebalance(rebRes.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load portfolio");
    } finally {
      setLoading(false);
    }
  }, [orderLimit]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const fmtRp = (v: number) => `Rp ${v.toLocaleString("id-ID", { maximumFractionDigits: 0 })}`;
  const fmtPct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-zinc-200">Portfolio</h2>
        <button
          onClick={fetchAll}
          disabled={loading}
          className="border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {error && <div className="border border-red-800 bg-red-950/20 p-2 text-xs text-red-400">{error}</div>}

      {/* Exposure summary */}
      {exposure && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="TOTAL EQUITY" value={fmtRp(exposure.total_equity)} />
          <Stat label="CASH" value={fmtRp(exposure.cash)} sub={`${(100 - exposure.exposure_pct).toFixed(1)}%`} />
          <Stat
            label="INVESTED"
            value={fmtRp(exposure.invested)}
            sub={`${exposure.exposure_pct.toFixed(1)}%`}
            valueClass={exposure.exposure_pct > 0 ? "text-blue-400" : "text-zinc-400"}
          />
          <Stat label="POSITIONS" value={String(exposure.position_count)} />
        </div>
      )}

      {/* Performance metrics */}
      {performance && (
        <div className="border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="mb-2 text-[10px] text-zinc-500">PERFORMANCE METRICS</div>
          <div className="grid grid-cols-3 gap-3 lg:grid-cols-6">
            <Metric
              label="Total Return"
              value={fmtPct(performance.total_return)}
              className={performance.total_return >= 0 ? "text-green-400" : "text-red-400"}
            />
            <Metric label="Sharpe" value={performance.sharpe_ratio.toFixed(3)} />
            <Metric
              label="Max DD"
              value={`${performance.max_drawdown.toFixed(2)}%`}
              className="text-red-400"
            />
            <Metric label="Win Rate" value={`${performance.win_rate.toFixed(1)}%`} />
            <Metric label="Trades" value={String(performance.total_trades)} />
            <Metric label="Equity" value={fmtRp(performance.current_equity)} />
          </div>
          {performance.equity_curve.length > 1 && <EquityChart data={performance.equity_curve} />}
        </div>
      )}

      {/* Positions table */}
      <div className="border border-zinc-800 bg-zinc-900/50">
        <div className="border-b border-zinc-800 px-3 py-2 text-[10px] text-zinc-500">
          OPEN POSITIONS ({positions.length})
        </div>
        {positions.length > 0 ? (
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase text-zinc-500">
              <tr>
                <th className="px-2 py-1 text-left">Ticker</th>
                <th className="px-2 py-1 text-right">Shares</th>
                <th className="px-2 py-1 text-right">Avg Price</th>
                <th className="px-2 py-1 text-right">Current</th>
                <th className="px-2 py-1 text-right">Mkt Value</th>
                <th className="px-2 py-1 text-right">P&amp;L</th>
                <th className="px-2 py-1 text-right">P&amp;L %</th>
                <th className="px-2 py-1 text-right">Stop Loss</th>
                <th className="px-2 py-1 text-right">Take Profit</th>
                <th className="px-2 py-1 text-left">Status</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => (
                <tr key={p.ticker + i} className="border-t border-zinc-800/60 hover:bg-zinc-800/30">
                  <td className="px-2 py-1 font-mono text-zinc-100">{p.ticker}</td>
                  <td className="px-2 py-1 text-right font-mono text-zinc-300">
                    {p.shares.toLocaleString()}
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-zinc-300">
                    {p.avg_price.toLocaleString()}
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-zinc-300">
                    {p.current_price?.toLocaleString() ?? "—"}
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-zinc-300">
                    {p.market_value ? fmtRp(p.market_value) : "—"}
                  </td>
                  <td
                    className={`px-2 py-1 text-right font-mono ${
                      (p.unrealized_pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400"
                    }`}
                  >
                    {p.unrealized_pnl != null ? fmtRp(p.unrealized_pnl) : "—"}
                  </td>
                  <td
                    className={`px-2 py-1 text-right font-mono ${
                      (p.unrealized_pnl_pct ?? 0) >= 0 ? "text-green-400" : "text-red-400"
                    }`}
                  >
                    {p.unrealized_pnl_pct != null ? fmtPct(p.unrealized_pnl_pct) : "—"}
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-amber-400/70">
                    {p.stop_loss?.toLocaleString() ?? "—"}
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-green-500/70">
                    {p.take_profit?.toLocaleString() ?? "—"}
                  </td>
                  <td className="px-2 py-1 text-zinc-400">{p.status ?? "open"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="px-3 py-6 text-center text-xs text-zinc-600">
            No open positions. Capital is fully in cash.
          </div>
        )}
      </div>

      {/* Rebalance status */}
      {rebalance && (
        <div className="border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[10px] text-zinc-500">REBALANCE STATUS</span>
            <span
              className={`text-[10px] ${rebalance.enabled ? "text-green-400" : "text-zinc-500"}`}
            >
              {rebalance.enabled ? "ENABLED" : "DISABLED"}
            </span>
            <span className="text-[10px] text-zinc-600">· frequency: {rebalance.frequency}</span>
          </div>
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase text-zinc-500">
              <tr>
                <th className="px-2 py-1 text-left">Ticker</th>
                <th className="px-2 py-1 text-right">Target Weight</th>
                <th className="px-2 py-1 text-right">Current Weight</th>
                <th className="px-2 py-1 text-right">Drift</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(rebalance.target_weights).map(([ticker, target]) => {
                const current = rebalance.current_weights[ticker] ?? 0;
                const drift = rebalance.drift[ticker] ?? 0;
                return (
                  <tr key={ticker} className="border-t border-zinc-800/60">
                    <td className="px-2 py-1 font-mono text-zinc-100">{ticker}</td>
                    <td className="px-2 py-1 text-right font-mono text-zinc-300">
                      {(target * 100).toFixed(1)}%
                    </td>
                    <td className="px-2 py-1 text-right font-mono text-zinc-300">
                      {(current * 100).toFixed(1)}%
                    </td>
                    <td
                      className={`px-2 py-1 text-right font-mono ${
                        Math.abs(drift) > 0.05 ? "text-amber-400" : "text-zinc-500"
                      }`}
                    >
                      {drift >= 0 ? "+" : ""}
                      {(drift * 100).toFixed(2)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Order history */}
      <div className="border border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center border-b border-zinc-800 px-3 py-2">
          <span className="text-[10px] text-zinc-500">ORDER HISTORY ({orders.length})</span>
          <label className="ml-auto flex items-center gap-1 text-[10px] text-zinc-500">
            limit
            <input
              type="number"
              min={5}
              max={100}
              value={orderLimit}
              onChange={(e) => setOrderLimit(Number(e.target.value) || 20)}
              className="w-16 border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>
        </div>
        {orders.length > 0 ? (
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase text-zinc-500">
              <tr>
                <th className="px-2 py-1 text-left">Time</th>
                <th className="px-2 py-1 text-left">Ticker</th>
                <th className="px-2 py-1 text-left">Side</th>
                <th className="px-2 py-1 text-right">Shares</th>
                <th className="px-2 py-1 text-right">Price</th>
                <th className="px-2 py-1 text-left">Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o, i) => (
                <tr key={i} className="border-t border-zinc-800/60 hover:bg-zinc-800/30">
                  <td className="px-2 py-1 text-zinc-400">
                    {o.timestamp ? new Date(o.timestamp).toLocaleString("id-ID") : "—"}
                  </td>
                  <td className="px-2 py-1 font-mono text-zinc-100">{o.ticker ?? "—"}</td>
                  <td
                    className={`px-2 py-1 font-mono ${
                      o.side === "BUY" ? "text-green-400" : o.side === "SELL" ? "text-red-400" : "text-zinc-400"
                    }`}
                  >
                    {o.side ?? "—"}
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-zinc-300">
                    {o.shares?.toLocaleString() ?? "—"}
                  </td>
                  <td className="px-2 py-1 text-right font-mono text-zinc-300">
                    {o.price?.toLocaleString() ?? "—"}
                  </td>
                  <td className="px-2 py-1 text-zinc-400">{o.status ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="px-3 py-6 text-center text-xs text-zinc-600">No orders yet.</div>
        )}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  valueClass = "text-zinc-100",
}: {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <div className="border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="text-[10px] text-zinc-500">{label}</div>
      <div className={`text-lg font-mono ${valueClass}`}>{value}</div>
      {sub && <div className="text-[10px] text-zinc-600">{sub}</div>}
    </div>
  );
}

function Metric({ label, value, className = "text-zinc-100" }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <div className="text-[10px] text-zinc-500">{label}</div>
      <div className={`font-mono text-sm ${className}`}>{value}</div>
    </div>
  );
}

function EquityChart({ data }: { data: { date: string; equity: number }[] }) {
  const w = 800;
  const h = 120;
  const pad = 20;
  const cw = w - pad * 2;
  const ch = h - pad * 2;
  const vals = data.map((d) => d.equity);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const points = data
    .map((d, i) => {
      const x = pad + (i / (data.length - 1)) * cw;
      const y = pad + ch - ((d.equity - min) / range) * ch;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <div className="mt-3">
      <div className="mb-1 text-[10px] text-zinc-500">EQUITY CURVE</div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ maxWidth: "100%" }}>
        <polyline points={points} fill="none" stroke="#3b82f6" strokeWidth="1.5" />
        <text x={pad} y={pad - 5} fill="#71717a" fontSize="10" fontFamily="monospace">
          {max.toLocaleString("id-ID", { maximumFractionDigits: 0 })}
        </text>
        <text x={pad} y={h - pad + 15} fill="#71717a" fontSize="10" fontFamily="monospace">
          {min.toLocaleString("id-ID", { maximumFractionDigits: 0 })}
        </text>
      </svg>
    </div>
  );
}
