"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import TerminalLayout from "../components/TerminalLayout";
import PriceChart from "../components/PriceChart";
import { apiFetch } from "../lib/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  AreaChart,
  Area,
} from "recharts";

interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  rsi?: number;
  macd?: number;
  macd_signal?: number;
  ma_20?: number;
  ma_50?: number;
  bb_upper?: number;
  bb_lower?: number;
}

interface ScoreData {
  engine: string;
  score: number;
}

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500 font-mono">{label}</div>
      <div className={`mt-1 text-lg font-semibold ${color || ""}`}>{value}</div>
      {sub && <div className="mt-1 text-[10px] text-zinc-400 font-mono">{sub}</div>}
    </div>
  );
}

interface Recommendation {
  action?: string;
  conviction_score?: number;
  position_size?: number;
  entry_price_range?: number[];
  stop_loss?: number;
  take_profit?: number;
  risk_flags?: string[];
}

interface Explanation {
  narrative?: string;
  top_factors?: [string, number][];
  confidence_interval?: number[];
}

interface Monitor {
  status?: string;
  tickers_in_db?: string[];
  score_count?: number;
  alerts?: unknown[];
}

interface ExecutionLog {
  type: string;
  ticker: string;
  action: string;
  quantity?: number;
  price?: number;
  total_value?: number;
  fee?: number;
  status: string;
  trigger?: string;
  timestamp: string;
  details?: string;
  conviction?: number;
}

interface RebalanceStatus {
  enabled: boolean;
  frequency: string;
  target_weights: Record<string, number>;
  current_weights: Record<string, number>;
  total_portfolio_value: number;
  drift: Record<string, number>;
}

interface AutoTradeToggle {
  auto_trade_enabled: boolean;
  capital: number;
  risk_per_trade: number;
  daily_loss_limit: number;
}

interface RebalanceToggle {
  rebalance_enabled: boolean;
  frequency: string;
  target_weights: string;
}

interface PerformanceData {
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
  current_equity: number;
  initial_capital: number;
  equity_curve: { date: string; equity: number }[];
}

export default function Dashboard() {
  const [ticker, setTicker] = useState("BBCA.JK");
  const [input, setInput] = useState("BBCA.JK");
  const [ohlcv, setOhlcv] = useState<Candle[]>([]);
  const [scores, setScores] = useState<ScoreData[]>([]);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState<string>("—");
  const [executionLogs, setExecutionLogs] = useState<ExecutionLog[]>([]);
  const [rebalanceStatus, setRebalanceStatus] = useState<RebalanceStatus | null>(null);
  const [rebalanceLoading, setRebalanceLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [autoTradeToggle, setAutoTradeToggle] = useState<AutoTradeToggle | null>(null);
  const [rebalanceToggle, setRebalanceToggle] = useState<RebalanceToggle | null>(null);
  const [togglingAutoTrade, setTogglingAutoTrade] = useState(false);
  const [togglingRebalance, setTogglingRebalance] = useState(false);
  const [performanceData, setPerformanceData] = useState<PerformanceData | null>(null);
  const [performancePeriod, setPerformancePeriod] = useState("1M");
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [rebalanceError, setRebalanceError] = useState("");

  const fetchPerformance = useCallback(async (period: string) => {
    try {
      const res = await apiFetch(`/api/performance?period=${period}`);
      if (res.ok) {
        setPerformanceData(await res.json());
      }
    } catch {
      // silent
    }
  }, []);

  const fetchWatchlist = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/watchlist`);
      if (res.ok) {
        const json = await res.json();
        setWatchlist(json.tickers || []);
      }
    } catch {
      // silent
    }
  }, []);

  const fetchExecutionLogs = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/execution/logs?limit=20`);
      if (res.ok) {
        const json = await res.json();
        setExecutionLogs(json.logs || []);
      }
    } catch {
      // silent
    }
  }, []);

  const fetchRebalanceStatus = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/rebalance/status`);
      if (res.ok) {
        setRebalanceStatus(await res.json());
      }
    } catch {
      // silent
    }
  }, []);

  const fetchAutoTradeToggle = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/execution/toggle`);
      if (res.ok) {
        setAutoTradeToggle(await res.json());
      }
    } catch {
      // silent
    }
  }, []);

  const fetchRebalanceToggle = useCallback(async () => {
    try {
      const res = await apiFetch(`/api/rebalance/toggle`);
      if (res.ok) {
        setRebalanceToggle(await res.json());
      }
    } catch {
      // silent
    }
  }, []);

  const toggleAutoTrade = async () => {
    setTogglingAutoTrade(true);
    try {
      const newValue = !autoTradeToggle?.auto_trade_enabled;
      const res = await apiFetch(`/api/execution/toggle`, {
        method: "POST",
        body: JSON.stringify({ enabled: newValue }),
      });
      if (res.ok) {
        const data = await res.json();
        setAutoTradeToggle(prev => prev ? { ...prev, auto_trade_enabled: data.auto_trade_enabled } : null);
      }
    } catch {
      // silent
    }
    setTogglingAutoTrade(false);
  };

  const toggleRebalance = async () => {
    setTogglingRebalance(true);
    try {
      const newValue = !rebalanceToggle?.rebalance_enabled;
      const res = await apiFetch(`/api/rebalance/toggle`, {
        method: "POST",
        body: JSON.stringify({ enabled: newValue }),
      });
      if (res.ok) {
        const data = await res.json();
        setRebalanceToggle(prev => prev ? { ...prev, rebalance_enabled: data.rebalance_enabled, frequency: data.frequency } : null);
      }
    } catch {
      // silent
    }
    setTogglingRebalance(false);
  };

  const triggerRebalance = async () => {
    setRebalanceLoading(true);
    setRebalanceError("");
    try {
      const res = await apiFetch(`/api/rebalance`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        await Promise.all([fetchExecutionLogs(), fetchRebalanceStatus()]);
      } else {
        setRebalanceError(`Rebalance failed: ${data.detail || "Unknown error"}`);
      }
    } catch (e) {
      setRebalanceError(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
    setRebalanceLoading(false);
  };

  // Auto-refresh execution logs every 15s, performance every 60s
  useEffect(() => {
    const init = async () => {
      await Promise.all([
        fetchExecutionLogs(),
        fetchRebalanceStatus(),
        fetchAutoTradeToggle(),
        fetchRebalanceToggle(),
        fetchPerformance(performancePeriod),
        fetchWatchlist(),
      ]);
    };
    init();
    if (!autoRefresh) return;
    const logInterval = setInterval(() => {
      fetchExecutionLogs();
    }, 15000);
    const perfInterval = setInterval(() => {
      fetchPerformance(performancePeriod);
    }, 60000);
    return () => {
      clearInterval(logInterval);
      clearInterval(perfInterval);
    };
  }, [autoRefresh, fetchExecutionLogs, fetchRebalanceStatus, fetchAutoTradeToggle, fetchRebalanceToggle, fetchPerformance, fetchWatchlist, performancePeriod]);

  useEffect(() => {
    let active = true;
    const run = async () => {
      setLoading(true);
      setError("");
      try {
        const [ohlcvRes, scoresRes, recRes, expRes, monRes] = await Promise.all([
          apiFetch(`/api/indicators/${ticker}`),
          apiFetch(`/api/scores/${ticker}`),
          apiFetch(`/api/recommend/${ticker}`),
          apiFetch(`/api/explain/${ticker}`),
          apiFetch(`/api/monitor`),
        ]);

        const ohlcvJson = await ohlcvRes.json();
        const scoresJson = await scoresRes.json();
        const recJson = await recRes.json();
        const expJson = await expRes.json();
        const monJson = await monRes.json();

        if (!active) return;

        if (ohlcvRes.ok) {
          setOhlcv(
            ohlcvJson.data.map((row: Record<string, unknown>) => ({
              time: (row.time as string),
              open: row.open as number,
              high: row.high as number,
              low: row.low as number,
              close: row.close as number,
              volume: (row.volume as number) ?? 0,
              rsi: row.rsi as number | undefined,
              macd: row.macd as number | undefined,
              macd_signal: row.macd_signal as number | undefined,
              ma_20: row.ma_20 as number | undefined,
              ma_50: row.ma_50 as number | undefined,
              bb_upper: row.bb_upper as number | undefined,
              bb_lower: row.bb_lower as number | undefined,
            }))
          );
        } else {
          setOhlcv([]);
        }

        if (scoresRes.ok) {
          const scoreList = Object.entries(scoresJson.scores || {}).map(
            ([engine, score]) => ({ engine, score: Number(score) })
          );
          setScores(scoreList);
        } else {
          setScores([]);
        }

        setRecommendation(recRes.ok ? recJson.recommendation : null);
        setExplanation(expRes.ok ? expJson : null);
        setMonitor(monRes.ok ? monJson : null);
        setLastUpdated(new Date().toLocaleString());
      } catch (e: unknown) {
        if (active) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (active) setLoading(false);
      }
    };
    run();
    return () => { active = false; };
  }, [ticker]);

  const metrics = useMemo(() => {
    if (!ohlcv.length) return null;
    const last = ohlcv[ohlcv.length - 1];
    const prev = ohlcv.length > 1 ? ohlcv[ohlcv.length - 2] : last;
    const change = last.close - prev.close;
    const changePct = prev.close ? (change / prev.close) * 100 : 0;
    const yearHigh = Math.max(...ohlcv.map((d) => d.high));
    const yearLow = Math.min(...ohlcv.map((d) => d.low));
    const avgVolume = Math.round(
      ohlcv.slice(-30).reduce((a, b) => a + b.volume, 0) / Math.min(30, ohlcv.length)
    );
    return { last, prev, change, changePct, yearHigh, yearLow, avgVolume };
  }, [ohlcv]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim()) setTicker(input.trim().toUpperCase());
  };

  const getActionColor = (action?: string) => {
    switch (action) {
      case "BUY":
        return "text-green-400";
      case "AVOID":
        return "text-red-400";
      default:
        return "text-yellow-400";
    }
  };

  const formatNumber = (n: number | null) =>
    n == null ? "—" : n.toLocaleString("id-ID", { maximumFractionDigits: 2 });

  return (
    <TerminalLayout active="dashboard" ticker={ticker}>
      <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-baseline md:justify-between">
        <h1 className="text-xl font-bold tracking-tight text-zinc-100">
          TRADING SYSTEM
        </h1>
        <form onSubmit={handleSubmit} className="flex gap-2 font-mono">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ticker (e.g. BBCA.JK)"
            className="border border-zinc-800 bg-zinc-900 px-3 py-1 text-xs outline-none focus:border-blue-500"
          />
          <button
            type="submit"
            disabled={loading}
            className="border border-blue-600 bg-blue-600/20 px-3 py-1 text-xs font-medium text-blue-300 hover:bg-blue-600/30 disabled:opacity-50"
          >
            {loading ? "..." : "ANALYZE"}
          </button>
        </form>
      </div>

      {error && (
        <div className="mb-4 border border-red-900/50 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <section className="mb-4 grid grid-cols-2 gap-1 lg:grid-cols-4 xl:grid-cols-8">
        <StatCard
          label="Ticker"
          value={ticker}
          sub={metrics ? `Last: ${lastUpdated}` : "—"}
        />
        <StatCard
          label="Last Price"
          value={metrics ? formatNumber(metrics.last.close) : "—"}
          sub={metrics ? `Prev ${formatNumber(metrics.prev.close)}` : undefined}
        />
        <StatCard
          label="Daily Change"
          value={
            metrics ? (
              <span className={metrics.change >= 0 ? "text-green-400" : "text-red-400"}>
                {`${metrics.change >= 0 ? "+" : ""}${formatNumber(metrics.change)}`}
              </span>
            ) : (
              "—"
            )
          }
        />
        <StatCard
          label="Change %"
          value={
            metrics ? (
              <span className={metrics.changePct >= 0 ? "text-green-400" : "text-red-400"}>
                {`${metrics.changePct >= 0 ? "+" : ""}${formatNumber(metrics.changePct)}%`}
              </span>
            ) : (
              "—"
            )
          }
        />
        <StatCard
          label="Today's Range"
          value={
            metrics
              ? `${formatNumber(metrics.last.low)} - ${formatNumber(metrics.last.high)}`
              : "—"
          }
        />
        <StatCard
          label="52W Range"
          value={
            metrics
              ? `${formatNumber(metrics.yearLow)} - ${formatNumber(metrics.yearHigh)}`
              : "—"
          }
        />
        <StatCard
          label="Action"
          value={recommendation?.action || "—"}
          color={getActionColor(recommendation?.action)}
        />
        <StatCard
          label="Conviction"
          value={recommendation?.conviction_score ?? "—"}
        />
      </section>

      <div className="grid flex-1 grid-cols-1 gap-2 lg:grid-cols-3">
        <section className="border border-zinc-800 bg-zinc-900/30 p-3 lg:col-span-2">
          <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-zinc-500 font-mono">Price Chart</h2>
          <PriceChart data={ohlcv} />
        </section>

        <section className="border border-zinc-800 bg-zinc-900/30 p-3">
          <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-zinc-500 font-mono">Factor Scores</h2>
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={scores} layout="vertical" margin={{ left: 20 }}>
                <XAxis type="number" domain={[0, 100]} hide />
                <YAxis
                  dataKey="engine"
                  type="category"
                  width={80}
                  tick={{ fill: "#9ca3af", fontSize: 10 }}
                />
                <Tooltip
                  contentStyle={{
                    background: "#18181b",
                    border: "1px solid #27272a",
                  }}
                  itemStyle={{ color: "#e4e4e7" }}
                />
                <Bar dataKey="score" radius={[0, 4, 4, 0]}>
                  {scores.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={
                        entry.score >= 70
                          ? "#22c55e"
                          : entry.score >= 40
                            ? "#facc15"
                            : "#ef4444"
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-3">
        <section className="border border-zinc-800 bg-zinc-900/30 p-3">
          <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-zinc-500 font-mono">Recommendation</h2>
          {recommendation ? (
            <dl className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="text-zinc-500">Position Size</div>
              <div className="text-zinc-200">{recommendation.position_size}</div>
              <div className="text-zinc-500">Entry Range</div>
              <div className="text-zinc-200">{recommendation.entry_price_range?.join(" - ")}</div>
              <div className="text-zinc-500">Stop Loss</div>
              <div className="text-zinc-200">{recommendation.stop_loss}</div>
              <div className="text-zinc-500">Take Profit</div>
              <div className="text-zinc-200">{recommendation.take_profit}</div>
              <div className="text-zinc-500">Risk Flags</div>
              <div className="text-zinc-200">
                {recommendation.risk_flags?.length
                  ? recommendation.risk_flags.join(", ")
                  : "None"}
              </div>
            </dl>
          ) : (
            <p className="text-zinc-500 text-xs">No recommendation available.</p>
          )}
        </section>

        <section className="border border-zinc-800 bg-zinc-900/30 p-3 lg:col-span-2">
          <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-zinc-500 font-mono">Explanation</h2>
          {explanation ? (
            <div className="space-y-2 text-xs font-mono text-zinc-300">
              <p>{explanation.narrative}</p>
              <div>
                <div className="mb-1 text-zinc-500">Top Factors</div>
                <ul className="list-disc pl-5">
                  {explanation.top_factors?.map(([name, value]: [string, number]) => (
                    <li key={name}>
                      {name}: {value}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="mb-1 text-zinc-500">Confidence Interval</div>
                <div className="text-zinc-200">{explanation.confidence_interval?.join(" - ")}</div>
              </div>
            </div>
          ) : (
            <p className="text-zinc-500 text-xs">No explanation available.</p>
          )}
        </section>
      </div>

      <section className="mt-2 border border-zinc-800 bg-zinc-900/30 p-3">
        <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-zinc-500 font-mono">System Health</h2>
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4 text-xs font-mono">
          <div className="border border-zinc-800 bg-zinc-900/50 p-2">
            <div className="text-zinc-500">API Status</div>
            <div className="text-zinc-200">{monitor?.status || "—"}</div>
          </div>
          <div className="border border-zinc-800 bg-zinc-900/50 p-2">
            <div className="text-zinc-500">Tickers in DB</div>
            <div className="text-zinc-200">{monitor?.tickers_in_db?.length || 0}</div>
          </div>
          <div className="border border-zinc-800 bg-zinc-900/50 p-2">
            <div className="text-zinc-500">Scores Computed</div>
            <div className="text-zinc-200">{monitor?.score_count || 0}</div>
          </div>
          <div className="border border-zinc-800 bg-zinc-900/50 p-2">
            <div className="text-zinc-500">Active Alerts</div>
            <div className="text-zinc-200">{monitor?.alerts?.length || 0}</div>
          </div>
        </div>
        {monitor?.tickers_in_db && monitor.tickers_in_db.length > 0 && (
          <div className="mt-2">
            <div className="mb-1 text-zinc-500 text-xs font-mono">Available tickers</div>
            <div className="flex flex-wrap gap-1">
              {monitor.tickers_in_db.map((t: string) => (
                <button
                  key={t}
                  onClick={() => {
                    setInput(t);
                    setTicker(t);
                  }}
                  className="border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-300 hover:bg-zinc-700"
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* ===== PERFORMANCE ANALYTICS ===== */}
      {performanceData && performanceData.equity_curve?.length > 0 && (
        <section className="mt-2 border border-zinc-800 bg-zinc-900/30 p-3">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wide text-zinc-500 font-mono">Performance Analytics</h2>
            <div className="flex gap-1">
              {["1W", "1M", "3M", "6M", "1Y", "ALL"].map((p) => (
                <button
                  key={p}
                  onClick={() => setPerformancePeriod(p)}
                  className={`px-2 py-0.5 text-[10px] font-mono ${
                    performancePeriod === p
                      ? "border border-blue-500 bg-blue-500/20 text-blue-300"
                      : "border border-zinc-700 bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Metric Cards */}
          <div className="mb-3 grid grid-cols-2 gap-1 lg:grid-cols-5">
            <div className="border border-zinc-800 bg-zinc-900/50 p-2">
              <div className="text-[10px] uppercase text-zinc-500 font-mono">Total Return</div>
              <div className={`mt-1 text-lg font-bold ${performanceData.total_return >= 0 ? "text-green-400" : "text-red-400"}`}>
                {performanceData.total_return >= 0 ? "+" : ""}{performanceData.total_return.toFixed(2)}%
              </div>
            </div>
            <div className="border border-zinc-800 bg-zinc-900/50 p-2">
              <div className="text-[10px] uppercase text-zinc-500 font-mono">Sharpe Ratio</div>
              <div className="mt-1 text-lg font-bold text-zinc-200">{performanceData.sharpe_ratio.toFixed(2)}</div>
            </div>
            <div className="border border-zinc-800 bg-zinc-900/50 p-2">
              <div className="text-[10px] uppercase text-zinc-500 font-mono">Max Drawdown</div>
              <div className="mt-1 text-lg font-bold text-red-400">{performanceData.max_drawdown.toFixed(2)}%</div>
            </div>
            <div className="border border-zinc-800 bg-zinc-900/50 p-2">
              <div className="text-[10px] uppercase text-zinc-500 font-mono">Win Rate</div>
              <div className="mt-1 text-lg font-bold text-zinc-200">{performanceData.win_rate.toFixed(1)}%</div>
            </div>
            <div className="border border-zinc-800 bg-zinc-900/50 p-2">
              <div className="text-[10px] uppercase text-zinc-500 font-mono">Total Trades</div>
              <div className="mt-1 text-lg font-bold text-zinc-200">{performanceData.total_trades}</div>
            </div>
          </div>

          {/* Equity Curve */}
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={performanceData.equity_curve}>
                <defs>
                  <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8884d8" stopOpacity={0.8} />
                    <stop offset="95%" stopColor="#8884d8" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" stroke="#666" fontSize={9} tickFormatter={(d: string) => d.slice(5)} />
                <YAxis stroke="#666" fontSize={9} domain={["auto", "auto"]} />
                <Tooltip
                  formatter={(value: unknown) => `Rp ${Number(value).toLocaleString("id-ID", { maximumFractionDigits: 0 })}`}
                  contentStyle={{ background: "#18181b", border: "1px solid #27272a" }}
                  itemStyle={{ color: "#e4e4e7" }}
                />
                <Area type="monotone" dataKey="equity" stroke="#8884d8" fillOpacity={1} fill="url(#equityGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {/* ===== WATCHLIST ===== */}
      {watchlist.length > 0 && (
        <section className="mt-2 border border-zinc-800 bg-zinc-900/30 p-3">
          <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-zinc-500 font-mono">Watchlist</h2>
          <div className="flex flex-wrap gap-1">
            {watchlist.map((t) => (
              <button
                key={t}
                onClick={() => {
                  setInput(t);
                  setTicker(t);
                }}
                className="border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-300 hover:bg-zinc-700"
              >
                {t}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* ===== EXECUTION LOG & REBALANCE ===== */}
      <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-3">
        {/* Execution Log (2 cols) */}
        <section className="border border-zinc-800 bg-zinc-900/30 p-3 lg:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wide text-zinc-500 font-mono">Execution Log</h2>
            <div className="flex items-center gap-3">
              {/* Auto-Trade Toggle */}
              <button
                onClick={toggleAutoTrade}
                disabled={togglingAutoTrade}
                className={`flex items-center gap-1.5 rounded px-2 py-0.5 text-[10px] font-mono transition-colors ${
                  autoTradeToggle?.auto_trade_enabled
                    ? "bg-green-900/50 text-green-300 border border-green-700"
                    : "bg-zinc-800 text-zinc-400 border border-zinc-700"
                } disabled:opacity-50`}
              >
                <span className={`inline-block h-2 w-2 rounded-full ${autoTradeToggle?.auto_trade_enabled ? "bg-green-400" : "bg-zinc-500"}`} />
                Auto-Trade {autoTradeToggle?.auto_trade_enabled ? "ON" : "OFF"}
              </button>
              <label className="flex items-center gap-1 text-[10px] text-zinc-500 font-mono">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                  className="accent-blue-500"
                />
                Auto-refresh
              </label>
              <button
                onClick={fetchExecutionLogs}
                className="border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-300 hover:bg-zinc-700"
              >
                Refresh
              </button>
            </div>
          </div>
          <div className="max-h-64 overflow-y-auto">
            {executionLogs.length > 0 ? (
              executionLogs.map((log, idx) => (
                <div
                  key={idx}
                  className={`flex items-center gap-2 border-b border-zinc-800/50 px-2 py-1.5 text-[10px] font-mono ${
                    log.type === "ORDER" ? "border-l-2 border-l-blue-500" : "border-l-2 border-l-yellow-500"
                  }`}
                >
                  <span className="w-16 flex-shrink-0 text-zinc-500">
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </span>
                  <span
                    className={`px-1.5 py-0.5 text-[9px] font-bold ${
                      log.type === "ORDER" ? "bg-blue-950 text-blue-300" : "bg-yellow-950 text-yellow-300"
                    }`}
                  >
                    {log.type}
                  </span>
                  <span className="w-14 flex-shrink-0 font-bold text-zinc-200">{log.ticker}</span>
                  <span
                    className={`font-bold ${
                      log.action === "BUY" ? "text-green-400" : log.action === "SELL" ? "text-red-400" : "text-zinc-400"
                    }`}
                  >
                    {log.action}
                  </span>
                  <span className="flex-1 truncate text-zinc-400">
                    {log.type === "ORDER"
                      ? `${log.quantity} @ Rp ${log.price?.toFixed(2) || "0"}${log.trigger ? ` (${log.trigger})` : ""}`
                      : `Conviction: ${log.conviction || "N/A"}`}
                  </span>
                  <span
                    className={`px-1.5 py-0.5 text-[9px] ${
                      log.status === "FILLED" || log.status === "GENERATED" ? "bg-green-950 text-green-300" : "bg-zinc-800 text-zinc-400"
                    }`}
                  >
                    {log.status}
                  </span>
                </div>
              ))
            ) : (
              <div className="py-8 text-center text-zinc-600 text-xs">
                No execution logs yet. Run the automated execution engine or trigger a manual order.
              </div>
            )}
          </div>
        </section>

        {/* Rebalance Panel (1 col) */}
        <section className="border border-zinc-800 bg-zinc-900/30 p-3">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wide text-zinc-500 font-mono">Rebalancing</h2>
            {/* Rebalance Toggle */}
            <button
              onClick={toggleRebalance}
              disabled={togglingRebalance}
              className={`flex items-center gap-1.5 rounded px-2 py-0.5 text-[10px] font-mono transition-colors ${
                rebalanceToggle?.rebalance_enabled
                  ? "bg-purple-900/50 text-purple-300 border border-purple-700"
                  : "bg-zinc-800 text-zinc-400 border border-zinc-700"
              } disabled:opacity-50`}
            >
              <span className={`inline-block h-2 w-2 rounded-full ${rebalanceToggle?.rebalance_enabled ? "bg-purple-400" : "bg-zinc-500"}`} />
              {rebalanceToggle?.rebalance_enabled ? "ON" : "OFF"}
            </button>
          </div>
          <div className="space-y-2 text-[10px] font-mono">
            <div className="flex justify-between">
              <span className="text-zinc-500">Frequency</span>
              <span className="text-zinc-200">{rebalanceStatus?.frequency || "monthly"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Portfolio Value</span>
              <span className="text-zinc-200">
                Rp {(rebalanceStatus?.total_portfolio_value || 0).toLocaleString("id-ID", { maximumFractionDigits: 0 })}
              </span>
            </div>
            {rebalanceStatus?.target_weights && Object.entries(rebalanceStatus.target_weights).length > 0 ? (
              <div className="mt-2 space-y-1">
                <div className="text-zinc-500">Target Weights</div>
                {Object.entries(rebalanceStatus.target_weights).map(([ticker, weight]) => {
                  const current = rebalanceStatus.current_weights?.[ticker] || 0;
                  const drift = rebalanceStatus.drift?.[ticker] || 0;
                  return (
                    <div key={ticker} className="flex items-center justify-between">
                      <span className="text-zinc-300">{ticker}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-zinc-400">{(weight * 100).toFixed(0)}%</span>
                        <span className="text-zinc-600">vs</span>
                        <span className={drift > 0.05 ? "text-yellow-400" : "text-green-400"}>
                          {(current * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-zinc-600">No target weights configured.</div>
            )}
          </div>
          {rebalanceError && (
            <div className="mt-2 border border-red-800 bg-red-900/30 p-2 text-[10px] text-red-400">
              {rebalanceError}
            </div>
          )}
          <button
            onClick={triggerRebalance}
            disabled={rebalanceLoading}
            className="mt-3 w-full border border-purple-700 bg-purple-700/20 px-3 py-1.5 text-xs font-medium text-purple-300 hover:bg-purple-700/30 disabled:opacity-50"
          >
            {rebalanceLoading ? "Processing..." : "Run Rebalance Now"}
          </button>
        </section>
      </div>

      <footer className="mt-2 border border-zinc-800 bg-zinc-900/30 p-2 text-[10px] text-zinc-500 font-mono">
        <div className="flex items-center justify-between">
          <div className="flex gap-4">
            <span>Status: {monitor?.status || "—"}</span>
            <span>Tickers: {monitor?.tickers_in_db?.length || 0}</span>
            <span>Scores: {monitor?.score_count || 0}</span>
            <span>Alerts: {monitor?.alerts?.length || 0}</span>
          </div>
          <div>Rendered at {lastUpdated}</div>
        </div>
      </footer>
    </TerminalLayout>
  );
}
