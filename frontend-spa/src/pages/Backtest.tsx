import { useState } from "react";
import { apiFetch } from "../lib/api";

interface BacktestResult {
  ticker: string;
  strategy: string;
  final_equity: number;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
  equity_curve: { date: string; equity: number }[];
  metrics: Record<string, number>;
}

interface MonteCarloResult {
  ticker: string;
  status: string;
  n_simulations: number;
  mean_final_equity: number;
  median_final_equity: number;
  final_equity: { p5: number; p25: number; p50: number; p75: number; p95: number };
  prob_profit: number;
  prob_loss_20pct: number;
  worst_drawdown: number;
}

interface WalkForwardResult {
  ticker: string;
  strategy: string;
  status: string;
  n_splits: number;
  oos_mean_return: number;
  oos_std_return: number;
  oos_mean_sharpe: number;
  oos_positive_splits: number;
  oos_consistency: number;
  splits: { split: number; test_period: string; oos_return: number; oos_sharpe: number }[];
}

type Tab = "backtest" | "monte-carlo" | "walk-forward";

export default function Backtest() {
  const [tab, setTab] = useState<Tab>("backtest");
  const [ticker, setTicker] = useState("BBCA.JK");
  const [strategy, setStrategy] = useState("buy_and_hold");
  const [capital, setCapital] = useState(100000000);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  // MC params
  const [nSimulations, setNSimulations] = useState(1000);
  const [nPeriods, setNPeriods] = useState(252);
  const [blockSize, setBlockSize] = useState(0);

  // WF params
  const [nSplits, setNSplits] = useState(5);
  const [trainSize, setTrainSize] = useState(252);
  const [testSize, setTestSize] = useState(63);

  const [btResult, setBtResult] = useState<BacktestResult | null>(null);
  const [mcResult, setMcResult] = useState<MonteCarloResult | null>(null);
  const [wfResult, setWfResult] = useState<WalkForwardResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const runBacktest = async () => {
    setLoading(true);
    setError("");
    setBtResult(null);
    try {
      const body: Record<string, unknown> = { ticker, strategy, capital };
      if (start) body.start = start;
      if (end) body.end = end;
      const res = await apiFetch("/api/backtest", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setBtResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest failed");
    } finally {
      setLoading(false);
    }
  };

  const runMonteCarlo = async () => {
    setLoading(true);
    setError("");
    setMcResult(null);
    try {
      const body: Record<string, unknown> = {
        ticker,
        n_simulations: nSimulations,
        n_periods: nPeriods,
        capital,
      };
      if (blockSize > 0) body.block_size = blockSize;
      if (start) body.start = start;
      if (end) body.end = end;
      const res = await apiFetch("/api/backtest/monte-carlo", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setMcResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Monte Carlo failed");
    } finally {
      setLoading(false);
    }
  };

  const runWalkForward = async () => {
    setLoading(true);
    setError("");
    setWfResult(null);
    try {
      const body: Record<string, unknown> = {
        ticker,
        strategy,
        n_splits: nSplits,
        train_size: trainSize,
        test_size: testSize,
      };
      if (start) body.start = start;
      if (end) body.end = end;
      const res = await apiFetch("/api/backtest/walk-forward", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setWfResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Walk-forward failed");
    } finally {
      setLoading(false);
    }
  };

  const fmtRp = (v: number) => `Rp ${v.toLocaleString("id-ID", { maximumFractionDigits: 0 })}`;

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-bold text-zinc-200">Backtest &amp; Strategy Validation</h2>

      {/* Tab selector */}
      <div className="flex border border-zinc-700">
        {(["backtest", "monte-carlo", "walk-forward"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setError("");
            }}
            className={`px-4 py-1.5 text-xs capitalize ${
              tab === t ? "bg-blue-900/50 text-blue-300" : "text-zinc-400 hover:bg-zinc-800"
            }`}
          >
            {t.replace("-", " ")}
          </button>
        ))}
      </div>

      {/* Common config */}
      <div className="border border-zinc-800 bg-zinc-900/50 p-3 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1 text-xs text-zinc-400">
            Ticker
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              className="w-28 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>

          {(tab === "backtest" || tab === "walk-forward") && (
            <label className="flex items-center gap-1 text-xs text-zinc-400">
              Strategy
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
              >
                <option value="buy_and_hold">Buy &amp; Hold</option>
                <option value="ma_crossover">MA Crossover</option>
                <option value="conviction">Conviction</option>
              </select>
            </label>
          )}

          <label className="flex items-center gap-1 text-xs text-zinc-400">
            Capital
            <input
              type="number"
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value) || 100000000)}
              className="w-32 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>

          <label className="flex items-center gap-1 text-xs text-zinc-400">
            Start
            <input
              value={start}
              onChange={(e) => setStart(e.target.value)}
              placeholder="YYYY-MM-DD"
              className="w-28 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>

          <label className="flex items-center gap-1 text-xs text-zinc-400">
            End
            <input
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              placeholder="YYYY-MM-DD"
              className="w-28 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>

          {tab === "monte-carlo" && (
            <>
              <label className="flex items-center gap-1 text-xs text-zinc-400">
                Simulations
                <input
                  type="number"
                  value={nSimulations}
                  onChange={(e) => setNSimulations(Number(e.target.value) || 1000)}
                  className="w-20 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
                />
              </label>
              <label className="flex items-center gap-1 text-xs text-zinc-400">
                Periods
                <input
                  type="number"
                  value={nPeriods}
                  onChange={(e) => setNPeriods(Number(e.target.value) || 252)}
                  className="w-16 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
                />
              </label>
              <label className="flex items-center gap-1 text-xs text-zinc-400">
                Block size
                <input
                  type="number"
                  value={blockSize}
                  onChange={(e) => setBlockSize(Number(e.target.value) || 0)}
                  className="w-16 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
                />
              </label>
            </>
          )}

          {tab === "walk-forward" && (
            <>
              <label className="flex items-center gap-1 text-xs text-zinc-400">
                Splits
                <input
                  type="number"
                  value={nSplits}
                  onChange={(e) => setNSplits(Number(e.target.value) || 5)}
                  className="w-16 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
                />
              </label>
              <label className="flex items-center gap-1 text-xs text-zinc-400">
                Train
                <input
                  type="number"
                  value={trainSize}
                  onChange={(e) => setTrainSize(Number(e.target.value) || 252)}
                  className="w-16 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
                />
              </label>
              <label className="flex items-center gap-1 text-xs text-zinc-400">
                Test
                <input
                  type="number"
                  value={testSize}
                  onChange={(e) => setTestSize(Number(e.target.value) || 63)}
                  className="w-16 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
                />
              </label>
            </>
          )}

          <button
            onClick={() => (tab === "backtest" ? runBacktest() : tab === "monte-carlo" ? runMonteCarlo() : runWalkForward())}
            disabled={loading}
            className="border border-blue-700 bg-blue-900/30 px-4 py-1 text-xs text-blue-300 hover:bg-blue-900/50 disabled:opacity-50"
          >
            {loading ? "Running..." : "Run"}
          </button>
        </div>

        {error && <div className="text-xs text-red-400">{error}</div>}
      </div>

      {/* Results */}
      {tab === "backtest" && btResult && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat
              label="FINAL EQUITY"
              value={fmtRp(btResult.final_equity)}
              valueClass={btResult.total_return >= 0 ? "text-green-400" : "text-red-400"}
            />
            <Stat
              label="TOTAL RETURN"
              value={`${btResult.total_return >= 0 ? "+" : ""}${btResult.total_return}%`}
              valueClass={btResult.total_return >= 0 ? "text-green-400" : "text-red-400"}
            />
            <Stat label="SHARPE" value={btResult.sharpe_ratio.toFixed(3)} />
            <Stat label="MAX DRAWDOWN" value={`${btResult.max_drawdown}%`} valueClass="text-red-400" />
          </div>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="WIN RATE" value={`${btResult.win_rate}%`} />
            <Stat label="TRADES" value={String(btResult.total_trades)} />
            <Stat label="STRATEGY" value={btResult.strategy} />
            <Stat label="TICKER" value={btResult.ticker} />
          </div>
          {btResult.equity_curve.length > 1 && <EquityChart data={btResult.equity_curve} />}
        </div>
      )}

      {tab === "monte-carlo" && mcResult && (
        <div className="space-y-3">
          {mcResult.status === "insufficient_data" ? (
            <div className="border border-amber-800 bg-amber-950/20 p-3 text-xs text-amber-400">
              Insufficient data for Monte Carlo simulation.
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Stat label="SIMULATIONS" value={String(mcResult.n_simulations)} />
                <Stat
                  label="PROB PROFIT"
                  value={`${(mcResult.prob_profit * 100).toFixed(1)}%`}
                  valueClass={mcResult.prob_profit > 0.5 ? "text-green-400" : "text-red-400"}
                />
                <Stat
                  label="PROB LOSS >20%"
                  value={`${(mcResult.prob_loss_20pct * 100).toFixed(1)}%`}
                  valueClass="text-red-400"
                />
                <Stat
                  label="WORST DRAWDOWN"
                  value={`${(mcResult.worst_drawdown * 100).toFixed(2)}%`}
                  valueClass="text-red-400"
                />
              </div>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
                <Stat label="MEAN FINAL" value={fmtRp(mcResult.mean_final_equity)} />
                <Stat label="MEDIAN FINAL" value={fmtRp(mcResult.median_final_equity)} />
                <Stat label="P5 (WORST)" value={fmtRp(mcResult.final_equity.p5)} valueClass="text-red-400" />
                <Stat label="P25" value={fmtRp(mcResult.final_equity.p25)} />
                <Stat label="P75" value={fmtRp(mcResult.final_equity.p75)} />
                <Stat label="P95 (BEST)" value={fmtRp(mcResult.final_equity.p95)} valueClass="text-green-400" />
              </div>
            </>
          )}
        </div>
      )}

      {tab === "walk-forward" && wfResult && (
        <div className="space-y-3">
          {wfResult.status === "insufficient_data" || wfResult.status === "no_valid_splits" ? (
            <div className="border border-amber-800 bg-amber-950/20 p-3 text-xs text-amber-400">
              Insufficient data for walk-forward analysis: {wfResult.status}
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Stat
                  label="OOS MEAN RETURN"
                  value={`${(wfResult.oos_mean_return * 100).toFixed(2)}%`}
                  valueClass={wfResult.oos_mean_return >= 0 ? "text-green-400" : "text-red-400"}
                />
                <Stat label="OOS STD" value={`${(wfResult.oos_std_return * 100).toFixed(2)}%`} />
                <Stat
                  label="OOS SHARPE"
                  value={wfResult.oos_mean_sharpe.toFixed(3)}
                  valueClass={wfResult.oos_mean_sharpe > 0 ? "text-green-400" : "text-red-400"}
                />
                <Stat
                  label="CONSISTENCY"
                  value={`${(wfResult.oos_consistency * 100).toFixed(1)}%`}
                  valueClass={wfResult.oos_consistency > 0.5 ? "text-green-400" : "text-amber-400"}
                />
              </div>
              <div className="border border-zinc-800 bg-zinc-900/50">
                <div className="border-b border-zinc-800 px-3 py-2 text-[10px] text-zinc-500">
                  WALK-FORWARD SPLITS ({wfResult.n_splits}) · {wfResult.oos_positive_splits} positive
                </div>
                <table className="w-full text-xs">
                  <thead className="text-[10px] uppercase text-zinc-500">
                    <tr>
                      <th className="px-2 py-1 text-left">Split</th>
                      <th className="px-2 py-1 text-left">Test Period</th>
                      <th className="px-2 py-1 text-right">OOS Return</th>
                      <th className="px-2 py-1 text-right">OOS Sharpe</th>
                    </tr>
                  </thead>
                  <tbody>
                    {wfResult.splits.map((s) => (
                      <tr key={s.split} className="border-t border-zinc-800/60">
                        <td className="px-2 py-1 text-zinc-400">{s.split}</td>
                        <td className="px-2 py-1 text-zinc-300">{s.test_period}</td>
                        <td
                          className={`px-2 py-1 text-right font-mono ${
                            s.oos_return >= 0 ? "text-green-400" : "text-red-400"
                          }`}
                        >
                          {(s.oos_return * 100).toFixed(2)}%
                        </td>
                        <td
                          className={`px-2 py-1 text-right font-mono ${
                            s.oos_sharpe > 0 ? "text-green-400" : "text-red-400"
                          }`}
                        >
                          {s.oos_sharpe.toFixed(3)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  valueClass = "text-zinc-100",
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="text-[10px] text-zinc-500">{label}</div>
      <div className={`text-lg font-mono ${valueClass}`}>{value}</div>
    </div>
  );
}

function EquityChart({ data }: { data: { date: string; equity: number }[] }) {
  const w = 800;
  const h = 150;
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
    <div className="border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="mb-2 text-[10px] text-zinc-500">EQUITY CURVE ({data.length} points)</div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ maxWidth: "100%" }}>
        {[0, 0.25, 0.5, 0.75, 1].map((p) => (
          <line
            key={p}
            x1={pad}
            y1={pad + p * ch}
            x2={w - pad}
            y2={pad + p * ch}
            stroke="#27272a"
            strokeWidth="0.5"
          />
        ))}
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
