import { useCallback, useEffect, useRef, useState } from "react";
import { createChart, AreaSeries, type IChartApi, type ISeriesApi } from "lightweight-charts";

// --- Types ---

interface LogEntry {
  time: string;
  level: "INFO" | "PASS" | "FAIL" | "WARN" | "ERROR" | "STEP" | "DONE";
  message: string;
}

interface TestConfig {
  ticker: string;
  start_date: string;
  end_date: string;
  horizon: number;
  step: number;
  strategy: string;
  params: Record<string, number>;
}

interface TestSummary {
  ticker: string;
  strategy: string;
  total_predictions: number;
  correct_predictions: number;
  accuracy: number;
  buy_count: number;
  sell_count: number;
  hold_count: number;
  buy_accuracy: number;
  sell_accuracy: number;
  hold_accuracy: number;
  confusion_matrix: Record<string, Record<string, number>>;
  mean_actual_return: number;
  sharpe_of_predictions: number;
  final_equity: number;
  initial_equity: number;
}

interface TestResultRow {
  date: string;
  prediction: string;
  conviction: number;
  actual_return: number;
  actual_direction: string;
  correct: boolean;
  price_at_t: number;
  price_at_t_plus: number;
  indicators: Record<string, number | null>;
}

interface FullResult {
  config: TestConfig;
  summary: TestSummary;
  results: TestResultRow[];
  equity_curve: { date: string; equity: number }[];
}

type RunState = "idle" | "running" | "done" | "error";

const STRATEGIES = [
  { value: "technical_rsi_sma", label: "RSI + SMA Crossover" },
  { value: "momentum", label: "MACD + ADX Momentum" },
  { value: "mean_reversion", label: "Bollinger Mean Reversion" },
];

const API_KEY = "dev-secret-key-2026";

export default function TestConsole() {
  // --- Config state ---
  const [ticker, setTicker] = useState("BBCA.JK");
  const [startDate, setStartDate] = useState("2025-01-01");
  const [endDate, setEndDate] = useState("2025-06-30");
  const [horizon, setHorizon] = useState(5);
  const [step, setStep] = useState(3);
  const [strategy, setStrategy] = useState("technical_rsi_sma");
  const [oversold, setOversold] = useState(35);
  const [overbought, setOverbought] = useState(70);

  // --- Run state ---
  const [runState, setRunState] = useState<RunState>("idle");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [summary, setSummary] = useState<TestSummary | null>(null);
  const [results, setResults] = useState<TestResultRow[]>([]);
  const [equityCurve, setEquityCurve] = useState<{ date: string; equity: number }[]>([]);
  const [error, setError] = useState("");

  // --- Refs ---
  const logEndRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi | null>(null);
  const equitySeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // --- Auto-scroll log ---
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // --- Chart setup ---
  useEffect(() => {
    if (!chartRef.current) return;
    const chart = createChart(chartRef.current, {
      width: chartRef.current.clientWidth,
      height: 200,
      layout: {
        background: { color: "#0a0a0a" },
        textColor: "#52525b",
        fontFamily: "monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "#18181b" },
        horzLines: { color: "#18181b" },
      },
      rightPriceScale: { borderColor: "#27272a" },
      timeScale: { borderColor: "#27272a", timeVisible: false },
    });
    chartApiRef.current = chart;
    return () => chart.remove();
  }, []);

  // --- Update equity chart when data changes ---
  useEffect(() => {
    if (!chartApiRef.current || !equitySeriesRef.current || equityCurve.length === 0) return;
    const data = equityCurve.map((d) => ({
      time: d.date as string,
      value: d.equity,
    }));
    equitySeriesRef.current.setData(data);
  }, [equityCurve]);

  // Create/replace equity series when chart is ready
  useEffect(() => {
    if (chartApiRef.current && !equitySeriesRef.current) {
      equitySeriesRef.current = chartApiRef.current.addSeries(AreaSeries, {
        lineColor: "#22c55e",
        topColor: "rgba(34,197,94,0.15)",
        bottomColor: "rgba(34,197,94,0)",
        lineWidth: 1,
      });
    }
  });

  const addLog = useCallback((level: LogEntry["level"], message: string) => {
    const time = new Date().toLocaleTimeString("id-ID", { hour12: false });
    setLogs((prev) => [...prev, { time, level, message }]);
  }, []);

  const reset = useCallback(() => {
    setLogs([]);
    setSummary(null);
    setResults([]);
    setEquityCurve([]);
    setProgress({ current: 0, total: 0 });
    setError("");
    setRunState("idle");
  }, []);

  const runTest = useCallback(async () => {
    reset();
    setRunState("running");
    addLog("INFO", `Initializing test harness...`);
    addLog("INFO", `Ticker: ${ticker} | Strategy: ${strategy}`);
    addLog("INFO", `Date range: ${startDate} → ${endDate} | Horizon: ${horizon}d | Step: ${step}d`);

    const config: TestConfig = {
      ticker,
      start_date: startDate,
      end_date: endDate,
      horizon,
      step,
      strategy,
      params: strategy === "technical_rsi_sma" ? { oversold, overbought } : {},
    };

    // Use WebSocket for streaming
    const wsUrl = `ws://${window.location.hostname}:8000/ws/test?token=${API_KEY}`;
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;
    } catch (e) {
      addLog("ERROR", `WebSocket connection failed: ${e}`);
      setRunState("error");
      return;
    }

    ws.onopen = () => {
      addLog("INFO", "WebSocket connected, sending config...");
      ws.send(JSON.stringify(config));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWsEvent(data);
      } catch {
        // ignore parse errors
      }
    };

    ws.onerror = () => {
      addLog("ERROR", "WebSocket error — falling back to HTTP POST");
      ws.close();
      runViaHttp(config);
    };

    ws.onclose = () => {
      if (runState === "running") {
        addLog("WARN", "WebSocket closed before completion — falling back to HTTP");
        runViaHttp(config);
      }
    };
  }, [ticker, startDate, endDate, horizon, step, strategy, oversold, overbought, reset, addLog, runState]);

  const handleWsEvent = useCallback(
    (data: Record<string, unknown>) => {
      const type = data.type as string;
      switch (type) {
        case "start": {
          const total = data.total as number;
          setProgress({ current: 0, total });
          addLog("INFO", `Test started: ${total} evaluation points, horizon=${data.horizon}d`);
          addLog("INFO", `Range: ${data.date_range}`);
          addLog("INFO", "");
          addLog("INFO", "  DATE       PRED     CONV   RETURN   DIR     STATUS   PRICE");
          addLog("INFO", "  ─────────  ───────  ─────  ───────  ─────── ───────  ────────");
          break;
        }
        case "step": {
          const cur = data.step as number;
          const tot = data.total as number;
          setProgress({ current: cur, total: tot });
          const status = data.status as string;
          const level: LogEntry["level"] = status === "PASS" ? "PASS" : "FAIL";
          addLog(
            level,
            `  ${data.date}  ${(data.prediction as string).padEnd(7)}  ${String(data.conviction).padEnd(5)}  ${String(data.actual_return).padStart(7)}%  ${(data.actual_direction as string).padEnd(6)} ${status.padEnd(7)} ${data.price}`,
          );
          break;
        }
        case "skip": {
          addLog("WARN", `  [${data.step}/${data.total}] ${data.date} SKIP: ${data.reason}`);
          break;
        }
        case "error":
        case "error_step": {
          addLog("ERROR", `  ${data.date || ""} ERROR: ${data.error || data.message}`);
          break;
        }
        case "done": {
          const s = data.summary as TestSummary;
          setSummary(s);
          addLog("INFO", "");
          addLog("DONE", `═══ TEST COMPLETE ═══`);
          addLog("DONE", `  Accuracy: ${s.accuracy.toFixed(2)}% (${s.correct_predictions}/${s.total_predictions})`);
          addLog("DONE", `  BUY: ${s.buy_count} (${s.buy_accuracy.toFixed(1)}%)  SELL: ${s.sell_count} (${s.sell_accuracy.toFixed(1)}%)  HOLD: ${s.hold_count} (${s.hold_accuracy.toFixed(1)}%)`);
          addLog("DONE", `  Mean actual return: ${s.mean_actual_return.toFixed(2)}%`);
          addLog("DONE", `  Final equity: Rp ${s.final_equity.toLocaleString("id-ID", { maximumFractionDigits: 0 })}`);
          setRunState("done");
          break;
        }
        case "final_result": {
          const result = data.result as FullResult;
          setResults(result.results);
          setEquityCurve(result.equity_curve);
          break;
        }
      }
    },
    [addLog],
  );

  const runViaHttp = useCallback(
    async (config: TestConfig) => {
      addLog("INFO", "Running via HTTP POST (no streaming)...");
      try {
        const res = await fetch("/api/test/prediction", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
          body: JSON.stringify(config),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as FullResult;
        setSummary(data.summary);
        setResults(data.results);
        setEquityCurve(data.equity_curve);
        setProgress({ current: data.results.length, total: data.results.length });
        addLog("DONE", `HTTP result: ${data.summary.accuracy.toFixed(2)}% accuracy (${data.summary.correct_predictions}/${data.summary.total_predictions})`);
        setRunState("done");
      } catch (e) {
        addLog("ERROR", `HTTP fallback failed: ${e}`);
        setRunState("error");
      }
    },
    [addLog],
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  const progressPct = progress.total > 0 ? (progress.current / progress.total) * 100 : 0;

  return (
    <div className="flex h-full flex-col bg-zinc-950 font-mono text-xs text-zinc-300">
      {/* === TOP BAR === */}
      <div className="border-b border-zinc-800 bg-black px-3 py-1.5 flex items-center gap-2">
        <span className="text-green-400 font-bold">TS-TEST</span>
        <span className="text-zinc-600">│</span>
        <span className="text-zinc-500">PREDICTION ACCURACY HARNESS</span>
        <span className="text-zinc-600">│</span>
        <span className={runState === "running" ? "text-amber-400 animate-pulse" : runState === "done" ? "text-green-400" : runState === "error" ? "text-red-400" : "text-zinc-500"}>
          {runState === "running" ? "● RUNNING" : runState === "done" ? "✓ DONE" : runState === "error" ? "✗ ERROR" : "○ IDLE"}
        </span>
        {progress.total > 0 && (
          <span className="text-zinc-500">
            [{progress.current}/{progress.total}] {progressPct.toFixed(0)}%
          </span>
        )}
        <span className="ml-auto text-zinc-600">{new Date().toLocaleString("id-ID")}</span>
      </div>

      {/* === MAIN BODY: 3-column layout === */}
      <div className="flex flex-1 overflow-hidden">
        {/* === LEFT: INPUT PANEL === */}
        <div className="w-64 border-r border-zinc-800 bg-zinc-950/50 overflow-y-auto p-3 space-y-3">
          <div className="text-[10px] uppercase text-zinc-600 tracking-wider">INPUT</div>

          <Field label="TICKER">
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              disabled={runState === "running"}
              className="w-full border border-zinc-700 bg-black px-2 py-1 text-green-400 outline-none focus:border-green-500 disabled:opacity-50"
            />
          </Field>

          <Field label="STRATEGY">
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              disabled={runState === "running"}
              className="w-full border border-zinc-700 bg-black px-2 py-1 text-green-400 outline-none focus:border-green-500 disabled:opacity-50"
            >
              {STRATEGIES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </Field>

          <Field label="START DATE">
            <input
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              placeholder="YYYY-MM-DD"
              disabled={runState === "running"}
              className="w-full border border-zinc-700 bg-black px-2 py-1 text-green-400 outline-none focus:border-green-500 disabled:opacity-50"
            />
          </Field>

          <Field label="END DATE">
            <input
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              placeholder="YYYY-MM-DD"
              disabled={runState === "running"}
              className="w-full border border-zinc-700 bg-black px-2 py-1 text-green-400 outline-none focus:border-green-500 disabled:opacity-50"
            />
          </Field>

          <div className="grid grid-cols-2 gap-2">
            <Field label="HORIZON">
              <input
                type="number"
                value={horizon}
                onChange={(e) => setHorizon(Number(e.target.value) || 5)}
                disabled={runState === "running"}
                className="w-full border border-zinc-700 bg-black px-2 py-1 text-green-400 outline-none focus:border-green-500 disabled:opacity-50"
              />
            </Field>
            <Field label="STEP">
              <input
                type="number"
                value={step}
                onChange={(e) => setStep(Number(e.target.value) || 1)}
                disabled={runState === "running"}
                className="w-full border border-zinc-700 bg-black px-2 py-1 text-green-400 outline-none focus:border-green-500 disabled:opacity-50"
              />
            </Field>
          </div>

          {strategy === "technical_rsi_sma" && (
            <div className="grid grid-cols-2 gap-2">
              <Field label="OVERSOLD">
                <input
                  type="number"
                  value={oversold}
                  onChange={(e) => setOversold(Number(e.target.value) || 35)}
                  disabled={runState === "running"}
                  className="w-full border border-zinc-700 bg-black px-2 py-1 text-green-400 outline-none focus:border-green-500 disabled:opacity-50"
                />
              </Field>
              <Field label="OVERBOUGHT">
                <input
                  type="number"
                  value={overbought}
                  onChange={(e) => setOverbought(Number(e.target.value) || 70)}
                  disabled={runState === "running"}
                  className="w-full border border-zinc-700 bg-black px-2 py-1 text-green-400 outline-none focus:border-green-500 disabled:opacity-50"
                />
              </Field>
            </div>
          )}

          <div className="pt-2 space-y-1">
            <button
              onClick={runTest}
              disabled={runState === "running"}
              className="w-full border border-green-700 bg-green-900/30 px-3 py-1.5 text-green-400 hover:bg-green-900/50 disabled:opacity-50"
            >
              {runState === "running" ? "▶ RUNNING..." : "▶ RUN TEST"}
            </button>
            <button
              onClick={reset}
              disabled={runState === "running"}
              className="w-full border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-zinc-400 hover:bg-zinc-800 disabled:opacity-50"
            >
              ○ RESET
            </button>
          </div>

          {/* Process diagram */}
          <div className="pt-3 border-t border-zinc-800 space-y-1 text-[10px] text-zinc-600">
            <div className="uppercase tracking-wider text-zinc-500">PROCESS FLOW</div>
            <div>1. Load OHLCV up to T (PIT-safe)</div>
            <div>2. Compute technical indicators</div>
            <div>3. Generate prediction (BUY/HOLD/SELL)</div>
            <div>4. Fast-forward T+{horizon}, get actual</div>
            <div>5. Compare: prediction vs actual</div>
            <div>6. Aggregate accuracy stats</div>
          </div>
        </div>

        {/* === CENTER: STREAMING LOG (terminal) === */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Progress bar */}
          {progress.total > 0 && (
            <div className="h-0.5 bg-zinc-800">
              <div
                className="h-full bg-green-500 transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          )}

          {/* Log output */}
          <div className="flex-1 overflow-y-auto bg-black p-3 text-[11px] leading-relaxed">
            {logs.length === 0 ? (
              <div className="text-zinc-700">
                <div className="text-green-700">$ ts-test --help</div>
                <div className="mt-2">Trading System Prediction Testing Harness</div>
                <div className="mt-1">Walk-forward validation: jalankan prediksi untuk tanggal lampau,</div>
                <div>bandingkan dengan hasil aktual, hitung akurasi.</div>
                <div className="mt-3 text-green-700">$ Configure input on left panel and click RUN TEST</div>
              </div>
            ) : (
              logs.map((entry, i) => (
                <div key={i} className="flex gap-2">
                  <span className="text-zinc-700 shrink-0">{entry.time}</span>
                  <span className={`shrink-0 w-10 ${levelColor(entry.level)}`}>
                    {entry.level}
                  </span>
                  <span className={levelTextColor(entry.level)}>{entry.message}</span>
                </div>
              ))
            )}
            <div ref={logEndRef} />
          </div>

          {/* Equity chart */}
          {equityCurve.length > 1 && (
            <div className="border-t border-zinc-800 bg-black p-2">
              <div className="text-[10px] text-zinc-600 mb-1">EQUITY CURVE (simulated, following predictions)</div>
              <div ref={chartRef} style={{ width: "100%", height: "180px" }} />
            </div>
          )}
        </div>

        {/* === RIGHT: OUTPUT / RESULTS === */}
        <div className="w-80 border-l border-zinc-800 bg-zinc-950/50 overflow-y-auto p-3 space-y-3">
          <div className="text-[10px] uppercase text-zinc-600 tracking-wider">OUTPUT</div>

          {error && <div className="text-red-400">{error}</div>}

          {/* Summary stats */}
          {summary ? (
            <>
              <div className="border border-zinc-800 bg-black p-3 space-y-2">
                <div className="text-[10px] text-zinc-600">SUMMARY</div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold text-green-400">{summary.accuracy.toFixed(1)}%</span>
                  <span className="text-zinc-500">accuracy</span>
                </div>
                <div className="text-[10px] text-zinc-500">
                  {summary.correct_predictions}/{summary.total_predictions} correct predictions
                </div>
                <div className="grid grid-cols-3 gap-2 pt-2 border-t border-zinc-800">
                  <Stat label="BUY" value={summary.buy_count} sub={`${summary.buy_accuracy.toFixed(0)}%`} color="text-green-400" />
                  <Stat label="HOLD" value={summary.hold_count} sub={`${summary.hold_accuracy.toFixed(0)}%`} color="text-zinc-400" />
                  <Stat label="SELL" value={summary.sell_count} sub={`${summary.sell_accuracy.toFixed(0)}%`} color="text-red-400" />
                </div>
              </div>

              {/* Confusion matrix */}
              <div className="border border-zinc-800 bg-black p-3">
                <div className="text-[10px] text-zinc-600 mb-2">CONFUSION MATRIX</div>
                <table className="w-full text-[10px]">
                  <thead>
                    <tr className="text-zinc-600">
                      <th className="text-left pb-1">Pred \ Actual</th>
                      <th className="text-right pb-1">UP</th>
                      <th className="text-right pb-1">FLAT</th>
                      <th className="text-right pb-1">DOWN</th>
                    </tr>
                  </thead>
                  <tbody>
                    {["BUY", "HOLD", "SELL"].map((pred) => {
                      const cm = summary.confusion_matrix[pred] || {};
                      return (
                        <tr key={pred} className="border-t border-zinc-800/50">
                          <td className={predColor(pred)}>{pred}</td>
                          <td className="text-right text-green-400/70">{cm.UP || 0}</td>
                          <td className="text-right text-zinc-500">{cm.FLAT || 0}</td>
                          <td className="text-right text-red-400/70">{cm.DOWN || 0}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Key metrics */}
              <div className="border border-zinc-800 bg-black p-3 space-y-1">
                <div className="text-[10px] text-zinc-600 mb-1">METRICS</div>
                <MetricRow label="Mean Actual Return" value={`${summary.mean_actual_return.toFixed(2)}%`} />
                <MetricRow label="Prediction Sharpe" value={summary.sharpe_of_predictions.toFixed(3)} />
                <MetricRow
                  label="Final Equity"
                  value={`Rp ${summary.final_equity.toLocaleString("id-ID", { maximumFractionDigits: 0 })}`}
                />
                <MetricRow
                  label="Total Return"
                  value={`${((summary.final_equity / summary.initial_equity - 1) * 100).toFixed(2)}%`}
                  color={summary.final_equity >= summary.initial_equity ? "text-green-400" : "text-red-400"}
                />
              </div>
            </>
          ) : (
            <div className="text-zinc-700 text-[10px]">
              Run a test to see results.
            </div>
          )}

          {/* Per-date results table */}
          {results.length > 0 && (
            <div className="border border-zinc-800 bg-black">
              <div className="text-[10px] text-zinc-600 p-2 border-b border-zinc-800">
                PER-DATE RESULTS ({results.length})
              </div>
              <div className="max-h-64 overflow-y-auto">
                <table className="w-full text-[10px]">
                  <thead className="text-zinc-600 sticky top-0 bg-black">
                    <tr>
                      <th className="text-left px-2 py-1">Date</th>
                      <th className="text-left px-1 py-1">Pred</th>
                      <th className="text-right px-1 py-1">Ret%</th>
                      <th className="text-center px-1 py-1">✓</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((r, i) => (
                      <tr key={i} className="border-t border-zinc-800/30 hover:bg-zinc-900/30">
                        <td className="px-2 py-0.5 text-zinc-500">{r.date}</td>
                        <td className={`px-1 py-0.5 ${predColor(r.prediction)}`}>{r.prediction}</td>
                        <td className={`px-1 py-0.5 text-right ${r.actual_return >= 0 ? "text-green-400/70" : "text-red-400/70"}`}>
                          {r.actual_return >= 0 ? "+" : ""}{r.actual_return.toFixed(2)}
                        </td>
                        <td className={`px-1 py-0.5 text-center ${r.correct ? "text-green-400" : "text-red-400"}`}>
                          {r.correct ? "✓" : "✗"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Helper components ---

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] text-zinc-600 mb-0.5">{label}</div>
      {children}
    </div>
  );
}

function Stat({ label, value, sub, color }: { label: string; value: number; sub: string; color: string }) {
  return (
    <div>
      <div className="text-[9px] text-zinc-600">{label}</div>
      <div className={`text-sm font-bold ${color}`}>{value}</div>
      <div className="text-[9px] text-zinc-500">{sub}</div>
    </div>
  );
}

function MetricRow({ label, value, color = "text-zinc-300" }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex justify-between text-[10px]">
      <span className="text-zinc-500">{label}</span>
      <span className={`font-mono ${color}`}>{value}</span>
    </div>
  );
}

// --- Color helpers ---

function levelColor(level: LogEntry["level"]): string {
  switch (level) {
    case "PASS": return "text-green-400";
    case "FAIL": return "text-red-400";
    case "WARN": return "text-amber-400";
    case "ERROR": return "text-red-500";
    case "DONE": return "text-blue-400";
    case "STEP": return "text-zinc-400";
    default: return "text-zinc-500";
  }
}

function levelTextColor(level: LogEntry["level"]): string {
  switch (level) {
    case "PASS": return "text-green-400/80";
    case "FAIL": return "text-red-400/80";
    case "WARN": return "text-amber-400/80";
    case "ERROR": return "text-red-500";
    case "DONE": return "text-blue-400";
    default: return "text-zinc-400";
  }
}

function predColor(pred: string): string {
  switch (pred) {
    case "BUY": return "text-green-400";
    case "SELL": return "text-red-400";
    default: return "text-zinc-400";
  }
}
