"use client";

import { useEffect, useMemo, useState } from "react";
import TerminalLayout from "../components/TerminalLayout";
import PriceChart from "../components/PriceChart";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
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

  useEffect(() => {
    let active = true;
    const run = async () => {
      setLoading(true);
      setError("");
      try {
        const [ohlcvRes, scoresRes, recRes, expRes, monRes] = await Promise.all([
          fetch(`/api/data/ohlcv?ticker=${ticker}`),
          fetch(`/api/scores/${ticker}`),
          fetch(`/api/recommend/${ticker}`),
          fetch(`/api/explain/${ticker}`),
          fetch(`/api/monitor`),
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
              time: (row.timestamp as string).split("T")[0],
              open: row.open as number,
              high: row.high as number,
              low: row.low as number,
              close: row.close as number,
              volume: (row.volume as number) ?? 0,
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
