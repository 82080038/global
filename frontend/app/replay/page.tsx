"use client";

import { useEffect, useState, useRef } from "react";
import TerminalLayout from "../components/TerminalLayout";
import { apiFetch } from "../lib/api";

interface DailyRecord {
  date: string;
  day: number;
  price: number;
  action: string;
  sell_trigger: string | null;
  conviction: number;
  scores: Record<string, number>;
  weights: Record<string, number>;
  regime: string | null;
  risk: {
    stop_loss: number;
    take_profit: number;
    atr: number;
    position_size: number;
    volatility: number;
    max_drawdown: number;
    risk_flags: string[];
    last_price: number;
  };
  portfolio: {
    cash: number;
    positions_value: number;
    equity: number;
    unrealized_pnl: number;
    total_return_pct: number;
    has_position: boolean;
    position_qty: number;
    position_entry: number | null;
    position_highest: number | null;
  };
  trade: {
    action: string;
    quantity: number;
    price: number;
    fees: number;
    realized_pnl?: number;
    trigger?: string;
  } | null;
}

interface TradeRecord {
  date: string;
  action: string;
  quantity: number;
  price: number;
  fees: number;
  realized_pnl?: number;
  trigger?: string;
}

interface EquityPoint {
  date: string;
  equity: number;
}

interface ReplayResult {
  ticker: string;
  initial_capital: number;
  final_equity: number;
  total_return_pct: number;
  total_realized_pnl: number;
  total_fees: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  n_trading_days: number;
  n_buys: number;
  n_sells: number;
  n_stop_loss: number;
  n_take_profit: number;
  n_trailing_stop: number;
  trades: TradeRecord[];
  equity_curve: EquityPoint[];
  daily_records: DailyRecord[];
}

interface TickerSummary {
  ticker: string;
  total_return_pct: number;
  final_equity: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  n_buys: number;
  n_sells: number;
  n_trading_days: number;
}

const ACTION_COLORS: Record<string, string> = {
  BUY: "#22c55e",
  SELL: "#ef4444",
  HOLD: "#f59e0b",
  WATCHLIST: "#3b82f6",
  AVOID: "#6b7280",
};

const SCORE_LABELS: Record<string, string> = {
  technical: "Technical",
  fundamental: "Fundamental",
  macro: "Macro",
  global: "Global",
  relationship: "Relationship",
  sentiment: "Sentiment",
};

export default function ReplayPage() {
  const [tickers, setTickers] = useState<TickerSummary[]>([]);
  const [selectedTicker, setSelectedTicker] = useState<string>("");
  const [result, setResult] = useState<ReplayResult | null>(null);
  const [currentDay, setCurrentDay] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(500); // ms per day
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const playRef = useRef<NodeJS.Timeout | null>(null);

  // Load ticker list (mount-only; initial selection set since selectedTicker starts empty)
  useEffect(() => {
    let active = true;
    apiFetch("/api/replay/list")
      .then((res) => res.json())
      .then((data) => {
        if (!active) return;
        setTickers(data.tickers || []);
        if (data.tickers?.length > 0) {
          setSelectedTicker(data.tickers[0].ticker);
        }
      })
      .catch(() => { });
    return () => { active = false; };
  }, []);

  // Load replay result when ticker changes
  useEffect(() => {
    if (!selectedTicker) return;
    let active = true;
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch(`/api/replay/${selectedTicker}`);
        if (!active) return;
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!active) return;
        setResult(data);
        setCurrentDay(0);
        setPlaying(false);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (active) setLoading(false);
      }
    };
    run();
    return () => { active = false; };
  }, [selectedTicker]);

  // Playback animation
  useEffect(() => {
    if (!playing || !result) return;
    if (currentDay >= result.daily_records.length - 1) {
      // Stop playback when the end is reached. Wrapped in a scheduled callback
      // (not called synchronously in the effect body) to avoid cascading renders.
      queueMicrotask(() => setPlaying(false));
      return;
    }
    playRef.current = setTimeout(() => {
      setCurrentDay((d) => Math.min(d + 1, result.daily_records.length - 1));
    }, speed);
    return () => {
      if (playRef.current) clearTimeout(playRef.current);
    };
  }, [playing, currentDay, result, speed]);

  const daily = result?.daily_records?.[currentDay];
  const equityUpTo = result?.equity_curve?.slice(0, currentDay + 1) || [];
  const tradesUpTo = result?.trades?.filter((t) => {
    const tradeDay = result.daily_records.findIndex(
      (d) => d.date === (t.date?.split("T")[0] || t.date)
    );
    return tradeDay >= 0 && tradeDay <= currentDay;
  }) || [];

  const formatIDR = (v: number) => `Rp ${v.toLocaleString("id-ID", { maximumFractionDigits: 0 })}`;

  return (
    <TerminalLayout active="dashboard" ticker={selectedTicker || "BBCA.JK"}>
      <div className="mb-4">
        <h1 className="mb-2 text-lg font-bold text-zinc-100">Replay Simulation</h1>
        <p className="text-xs text-zinc-500">
          Day-by-day replay using full pipeline: TechnicalAnalysis → DecisionEngine → RiskEngine → CostModel → Portfolio
        </p>
      </div>

      {/* Ticker selector */}
      <div className="mb-4 flex flex-wrap gap-2">
        {tickers.map((t) => (
          <button
            key={t.ticker}
            onClick={() => setSelectedTicker(t.ticker)}
            className={`rounded px-3 py-1 text-xs font-bold ${selectedTicker === t.ticker
              ? "bg-blue-600 text-white"
              : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
              }`}
          >
            {t.ticker} ({t.total_return_pct >= 0 ? "+" : ""}{t.total_return_pct.toFixed(2)}%)
          </button>
        ))}
      </div>

      {loading && <div className="text-xs text-zinc-500">Loading replay data...</div>}
      {error && <div className="text-xs text-red-400">Error: {error}</div>}

      {result && daily && (
        <>
          {/* Playback controls */}
          <div className="mb-4 rounded border border-zinc-800 bg-zinc-900/50 p-3">
            <div className="mb-2 flex items-center gap-3">
              <button
                onClick={() => setPlaying(!playing)}
                className="rounded bg-blue-600 px-4 py-1 text-xs font-bold text-white hover:bg-blue-500"
              >
                {playing ? "⏸ Pause" : "▶ Play"}
              </button>
              <button
                onClick={() => setCurrentDay(0)}
                className="rounded bg-zinc-700 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-600"
              >
                ⏮ Start
              </button>
              <button
                onClick={() => setCurrentDay(result.daily_records.length - 1)}
                className="rounded bg-zinc-700 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-600"
              >
                ⏭ End
              </button>
              <span className="text-xs text-zinc-400">
                Day {daily.day} / {result.n_trading_days}
              </span>
              <span className="text-xs text-zinc-500">|</span>
              <span className="text-xs text-zinc-400">Speed:</span>
              <select
                value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}
                className="rounded border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-100"
              >
                <option value={2000}>0.5x (slow)</option>
                <option value={1000}>1x (normal)</option>
                <option value={500}>2x (fast)</option>
                <option value={200}>5x (very fast)</option>
                <option value={50}>20x (turbo)</option>
              </select>
            </div>
            <input
              type="range"
              min={0}
              max={result.daily_records.length - 1}
              value={currentDay}
              onChange={(e) => {
                setCurrentDay(Number(e.target.value));
                setPlaying(false);
              }}
              className="w-full"
            />
          </div>

          {/* Main grid: 3 columns */}
          <div className="grid grid-cols-3 gap-4">
            {/* Column 1: Price + Action */}
            <div className="space-y-3">
              <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
                <div className="mb-2 text-xs font-bold text-zinc-300">PRICE & ACTION</div>
                <div className="mb-2 flex items-baseline gap-3">
                  <span className="text-2xl font-bold text-zinc-100">{daily.price.toLocaleString("id-ID")}</span>
                  <span className="text-xs text-zinc-500">{daily.date}</span>
                </div>
                <div
                  className="mb-3 rounded px-3 py-2 text-center text-lg font-bold"
                  style={{
                    background: `${ACTION_COLORS[daily.action]}22`,
                    color: ACTION_COLORS[daily.action],
                    border: `1px solid ${ACTION_COLORS[daily.action]}44`,
                  }}
                >
                  {daily.action}
                  {daily.sell_trigger && daily.sell_trigger !== "SIGNAL" && (
                    <span className="ml-2 text-xs">({daily.sell_trigger})</span>
                  )}
                </div>
                {/* Price chart (mini) */}
                <svg width="100%" height="120" viewBox="0 0 300 120">
                  {(() => {
                    const records = result.daily_records.slice(0, currentDay + 1);
                    if (records.length < 2) return null;
                    const prices = records.map((r) => r.price);
                    const minP = Math.min(...prices) * 0.98;
                    const maxP = Math.max(...prices) * 1.02;
                    const points = records
                      .map((r, i) => {
                        const x = (i / (records.length - 1)) * 290 + 5;
                        const y = 110 - ((r.price - minP) / (maxP - minP)) * 100;
                        return `${x},${y}`;
                      })
                      .join(" ");
                    // Buy/Sell markers
                    const markers = records
                      .filter((r) => r.trade)
                      .map((r) => {
                        const i = records.indexOf(r);
                        const x = (i / (records.length - 1)) * 290 + 5;
                        const y = 110 - ((r.price - minP) / (maxP - minP)) * 100;
                        const isBuy = r.trade!.action === "BUY";
                        return (
                          <g key={i}>
                            <circle cx={x} cy={y} r={4} fill={isBuy ? "#22c55e" : "#ef4444"} />
                            <text x={x} y={isBuy ? y + 15 : y - 8} fill={isBuy ? "#22c55e" : "#ef4444"} fontSize="8" textAnchor="middle">
                              {isBuy ? "B" : "S"}
                            </text>
                          </g>
                        );
                      });
                    return (
                      <>
                        <polyline points={points} fill="none" stroke="#3b82f6" strokeWidth="1.5" />
                        {markers}
                      </>
                    );
                  })()}
                </svg>
              </div>

              {/* Risk metrics */}
              <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
                <div className="mb-2 text-xs font-bold text-zinc-300">RISK METRICS</div>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Stop Loss</span>
                    <span className="text-red-400">{daily.risk.stop_loss.toLocaleString("id-ID")}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Take Profit</span>
                    <span className="text-green-400">{daily.risk.take_profit.toLocaleString("id-ID")}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">ATR(14)</span>
                    <span className="text-zinc-300">{daily.risk.atr.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Position Size</span>
                    <span className="text-zinc-300">{(daily.risk.position_size * 100).toFixed(2)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Volatility</span>
                    <span className="text-zinc-300">{(daily.risk.volatility * 100).toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Max Drawdown</span>
                    <span className="text-red-400">{(daily.risk.max_drawdown * 100).toFixed(2)}%</span>
                  </div>
                  {daily.risk.risk_flags.length > 0 && (
                    <div className="pt-1">
                      {daily.risk.risk_flags.map((flag) => (
                        <span key={flag} className="mr-1 rounded bg-red-900/50 px-2 py-0.5 text-xs text-red-400">
                          ⚠ {flag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Column 2: Analysis Scores + Decision */}
            <div className="space-y-3">
              <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
                <div className="mb-2 text-xs font-bold text-zinc-300">ANALYSIS SCORES (0-100)</div>
                <div className="space-y-2">
                  {Object.entries(daily.scores).map(([key, score]) => {
                    const weight = daily.weights[key] || 0;
                    const color = score >= 70 ? "#22c55e" : score >= 50 ? "#f59e0b" : "#ef4444";
                    return (
                      <div key={key}>
                        <div className="mb-0.5 flex justify-between text-xs">
                          <span className="text-zinc-400">
                            {SCORE_LABELS[key] || key}
                            <span className="ml-1 text-zinc-600">({(weight * 100).toFixed(1)}%)</span>
                          </span>
                          <span style={{ color }}>{score.toFixed(1)}</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded bg-zinc-800">
                          <div
                            className="h-full rounded transition-all"
                            style={{ width: `${score}%`, background: color }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Conviction gauge */}
              <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
                <div className="mb-2 text-xs font-bold text-zinc-300">CONVICTION & DECISION</div>
                <div className="mb-2 flex items-center gap-4">
                  <div className="relative h-20 w-20">
                    <svg width="80" height="80" viewBox="0 0 80 80">
                      <circle cx="40" cy="40" r="35" fill="none" stroke="#27272a" strokeWidth="6" />
                      <circle
                        cx="40" cy="40" r="35" fill="none"
                        stroke={daily.conviction >= 70 ? "#22c55e" : daily.conviction >= 55 ? "#3b82f6" : daily.conviction >= 40 ? "#f59e0b" : "#ef4444"}
                        strokeWidth="6"
                        strokeDasharray={`${(daily.conviction / 100) * 220} 220`}
                        transform="rotate(-90 40 40)"
                      />
                      <text x="40" y="45" textAnchor="middle" fill="#e0e0e0" fontSize="18" fontWeight="bold">
                        {daily.conviction.toFixed(0)}
                      </text>
                    </svg>
                  </div>
                  <div className="flex-1 space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Regime</span>
                      <span className="text-zinc-300">{daily.regime || "N/A"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Threshold BUY</span>
                      <span className="text-green-400">≥ 70</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Threshold SELL</span>
                      <span className="text-red-400">&lt; 40 (in pos)</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Decision</span>
                      <span style={{ color: ACTION_COLORS[daily.action] }} className="font-bold">
                        {daily.action}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Column 3: Portfolio + Trade */}
            <div className="space-y-3">
              <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
                <div className="mb-2 text-xs font-bold text-zinc-300">PORTFOLIO STATE</div>
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between border-b border-zinc-800 pb-1">
                    <span className="text-zinc-500">Cash</span>
                    <span className="text-zinc-200">{formatIDR(daily.portfolio.cash)}</span>
                  </div>
                  <div className="flex justify-between border-b border-zinc-800 pb-1">
                    <span className="text-zinc-500">Positions Value</span>
                    <span className="text-zinc-200">{formatIDR(daily.portfolio.positions_value)}</span>
                  </div>
                  <div className="flex justify-between border-b border-zinc-800 pb-1">
                    <span className="text-zinc-500">Total Equity</span>
                    <span className="text-lg font-bold text-zinc-100">{formatIDR(daily.portfolio.equity)}</span>
                  </div>
                  <div className="flex justify-between border-b border-zinc-800 pb-1">
                    <span className="text-zinc-500">Unrealized PnL</span>
                    <span className={daily.portfolio.unrealized_pnl >= 0 ? "text-green-400" : "text-red-400"}>
                      {daily.portfolio.unrealized_pnl >= 0 ? "+" : ""}{formatIDR(daily.portfolio.unrealized_pnl)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Total Return</span>
                    <span className={`text-lg font-bold ${daily.portfolio.total_return_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {daily.portfolio.total_return_pct >= 0 ? "+" : ""}{daily.portfolio.total_return_pct.toFixed(2)}%
                    </span>
                  </div>
                </div>
                {daily.portfolio.has_position && (
                  <div className="mt-3 rounded bg-zinc-800/50 p-2 text-xs">
                    <div className="mb-1 font-bold text-blue-400">OPEN POSITION</div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Shares</span>
                      <span className="text-zinc-300">{daily.portfolio.position_qty.toLocaleString("id-ID")}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Entry Price</span>
                      <span className="text-zinc-300">{daily.portfolio.position_entry?.toLocaleString("id-ID")}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Highest Since Entry</span>
                      <span className="text-zinc-300">{daily.portfolio.position_highest?.toLocaleString("id-ID")}</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Trade executed today */}
              <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
                <div className="mb-2 text-xs font-bold text-zinc-300">TRADE TODAY</div>
                {daily.trade ? (
                  <div className="space-y-1 text-xs">
                    <div className="rounded p-2" style={{ background: `${ACTION_COLORS[daily.trade.action]}22` }}>
                      <span className="font-bold" style={{ color: ACTION_COLORS[daily.trade.action] }}>
                        {daily.trade.action} {daily.trade.quantity.toLocaleString("id-ID")} shares
                      </span>
                      <span className="text-zinc-400"> @ {daily.trade.price.toLocaleString("id-ID")}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Fees</span>
                      <span className="text-zinc-300">{formatIDR(daily.trade.fees)}</span>
                    </div>
                    {daily.trade.realized_pnl !== undefined && (
                      <div className="flex justify-between">
                        <span className="text-zinc-500">Realized PnL</span>
                        <span className={daily.trade.realized_pnl >= 0 ? "text-green-400" : "text-red-400"}>
                          {daily.trade.realized_pnl >= 0 ? "+" : ""}{formatIDR(daily.trade.realized_pnl)}
                        </span>
                      </div>
                    )}
                    {daily.trade.trigger && (
                      <div className="flex justify-between">
                        <span className="text-zinc-500">Trigger</span>
                        <span className="text-zinc-300">{daily.trade.trigger}</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-xs text-zinc-600">No trade executed</div>
                )}
              </div>
            </div>
          </div>

          {/* Bottom: Equity curve + Trade log */}
          <div className="mt-4 grid grid-cols-2 gap-4">
            {/* Equity curve */}
            <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="mb-2 text-xs font-bold text-zinc-300">
                EQUITY CURVE (up to day {daily.day})
              </div>
              <svg width="100%" height="150" viewBox="0 0 500 150">
                {(() => {
                  if (equityUpTo.length < 2) return <text x="250" y="75" fill="#52525b" fontSize="12" textAnchor="middle">Not enough data</text>;
                  const equities = equityUpTo.map((e) => e.equity);
                  const minE = Math.min(...equities) * 0.99;
                  const maxE = Math.max(...equities) * 1.01;
                  const points = equityUpTo
                    .map((e, i) => {
                      const x = (i / (equityUpTo.length - 1)) * 490 + 5;
                      const y = 140 - ((e.equity - minE) / (maxE - minE)) * 130;
                      return `${x},${y}`;
                    })
                    .join(" ");
                  // Initial capital line
                  const initY = 140 - ((result.initial_capital - minE) / (maxE - minE)) * 130;
                  return (
                    <>
                      <line x1="5" y1={initY} x2="495" y2={initY} stroke="#52525b" strokeWidth="1" strokeDasharray="4 4" />
                      <text x="490" y={initY - 5} fill="#52525b" fontSize="9" textAnchor="end">Initial: {formatIDR(result.initial_capital)}</text>
                      <polyline points={points} fill="none" stroke="#22c55e" strokeWidth="2" />
                    </>
                  );
                })()}
              </svg>
            </div>

            {/* Trade log */}
            <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="mb-2 text-xs font-bold text-zinc-300">
                TRADE LOG ({tradesUpTo.length} trades so far)
              </div>
              <div className="max-h-40 overflow-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-zinc-500">
                      <th className="pb-1 text-left">Date</th>
                      <th className="pb-1 text-center">Action</th>
                      <th className="pb-1 text-right">Qty</th>
                      <th className="pb-1 text-right">Price</th>
                      <th className="pb-1 text-right">PnL</th>
                      <th className="pb-1 text-center">Trigger</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tradesUpTo.map((t, i) => (
                      <tr key={i} className="text-zinc-400">
                        <td className="py-0.5">{(t.date || "").split("T")[0]}</td>
                        <td className="py-0.5 text-center" style={{ color: ACTION_COLORS[t.action] || "#999" }}>
                          {t.action}
                        </td>
                        <td className="py-0.5 text-right">{t.quantity?.toLocaleString("id-ID")}</td>
                        <td className="py-0.5 text-right">{t.price?.toLocaleString("id-ID")}</td>
                        <td className="py-0.5 text-right" style={{ color: (t.realized_pnl || 0) >= 0 ? "#22c55e" : "#ef4444" }}>
                          {t.realized_pnl !== undefined ? `${t.realized_pnl >= 0 ? "+" : ""}${t.realized_pnl.toLocaleString("id-ID")}` : "-"}
                        </td>
                        <td className="py-0.5 text-center text-zinc-600">{t.trigger || "-"}</td>
                      </tr>
                    ))}
                    {tradesUpTo.length === 0 && (
                      <tr><td colSpan={6} className="py-2 text-center text-zinc-600">No trades yet</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Final summary (only on last day) */}
          {currentDay === result.daily_records.length - 1 && (
            <div className="mt-4 rounded border border-blue-800 bg-blue-900/20 p-4">
              <div className="mb-2 text-sm font-bold text-blue-400">SIMULATION COMPLETE</div>
              <div className="grid grid-cols-6 gap-3 text-xs">
                <div>
                  <div className="text-zinc-500">Final Equity</div>
                  <div className="text-lg font-bold text-zinc-100">{formatIDR(result.final_equity)}</div>
                </div>
                <div>
                  <div className="text-zinc-500">Total Return</div>
                  <div className={`text-lg font-bold ${result.total_return_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {result.total_return_pct >= 0 ? "+" : ""}{result.total_return_pct}%
                  </div>
                </div>
                <div>
                  <div className="text-zinc-500">Sharpe</div>
                  <div className="text-lg font-bold text-zinc-100">{result.sharpe_ratio.toFixed(4)}</div>
                </div>
                <div>
                  <div className="text-zinc-500">Max Drawdown</div>
                  <div className="text-lg font-bold text-red-400">{result.max_drawdown_pct}%</div>
                </div>
                <div>
                  <div className="text-zinc-500">Total Trades</div>
                  <div className="text-lg font-bold text-zinc-100">{result.n_buys}B / {result.n_sells}S</div>
                </div>
                <div>
                  <div className="text-zinc-500">SL/TP/TS</div>
                  <div className="text-lg font-bold text-zinc-100">
                    {result.n_stop_loss}/{result.n_take_profit}/{result.n_trailing_stop}
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </TerminalLayout>
  );
}
