"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import TerminalLayout from "../components/TerminalLayout";
import { apiFetch, APIError } from "../lib/api";

// ---------------------------------------------------------------------------
// Module registry — maps each engine/module to an API call for live testing.
// ---------------------------------------------------------------------------
type Category =
  | "data"
  | "analysis"
  | "decision"
  | "pipeline"
  | "risk"
  | "ai"
  | "execution"
  | "system";

interface ModuleDef {
  id: string;
  name: string;
  label: string;
  category: Category;
  description: string;
  method: "GET" | "POST";
  /** Build the API path. `ticker` may be empty for system-wide modules. */
  path: (ticker: string) => string;
  /** Optional request body builder for POST endpoints. */
  body?: (ticker: string) => Record<string, unknown>;
  /** Whether this module requires a ticker. */
  needsTicker?: boolean;
}

const MODULES: ModuleDef[] = [
  {
    id: "indicators",
    name: "technical",
    label: "Technical Indicators",
    category: "data",
    description: "OHLCV + RSI/MACD/MA/Bollinger via TechnicalAnalysisEngine",
    method: "GET",
    path: (t) => `/api/indicators/${encodeURIComponent(t)}`,
    needsTicker: true,
  },
  {
    id: "scores_load",
    name: "scores",
    label: "Scores (load)",
    category: "data",
    description: "Load persisted multi-factor scores from DB",
    method: "GET",
    path: (t) => `/api/scores/${encodeURIComponent(t)}`,
    needsTicker: true,
  },
  {
    id: "corporate",
    name: "corporate",
    label: "Corporate Actions",
    category: "data",
    description: "Splits & dividends via CorporateActionEngine",
    method: "GET",
    path: (t) => `/api/corporate/${encodeURIComponent(t)}`,
    needsTicker: true,
  },
  {
    id: "compute_scores",
    name: "pipeline",
    label: "Compute Scores (Pipeline)",
    category: "pipeline",
    description: "Run full AnalysisPipeline.compute() for ticker",
    method: "POST",
    path: () => `/api/scores/compute`,
    body: (t) => ({ ticker: t, period: "2y" }),
    needsTicker: true,
  },
  {
    id: "relationship",
    name: "relationship",
    label: "Market Relationship",
    category: "analysis",
    description: "Cross-asset / lead-lag via MarketRelationshipEngine",
    method: "GET",
    path: (t) => `/api/relationship/${encodeURIComponent(t)}`,
    needsTicker: true,
  },
  {
    id: "sentiment",
    name: "sentiment",
    label: "Sentiment (NLP)",
    category: "analysis",
    description: "Indonesian news NLP sentiment via SentimentEngine",
    method: "GET",
    path: (t) => `/api/sentiment/${encodeURIComponent(t)}`,
    needsTicker: true,
  },
  {
    id: "recommend",
    name: "decision",
    label: "Recommendation",
    category: "decision",
    description: "Multi-factor weighted decision via DecisionEngine",
    method: "GET",
    path: (t) => `/api/recommend/${encodeURIComponent(t)}`,
    needsTicker: true,
  },
  {
    id: "explain",
    name: "xai",
    label: "Explain (XAI)",
    category: "decision",
    description: "Narrative + top factors via ExplainableAIEngine",
    method: "GET",
    path: (t) => `/api/explain/${encodeURIComponent(t)}`,
    needsTicker: true,
  },
  {
    id: "risk_ticker",
    name: "risk",
    label: "Risk (ticker)",
    category: "risk",
    description: "VaR/CVaR/position sizing via RiskEngine",
    method: "GET",
    path: (t) => `/api/risk/${encodeURIComponent(t)}`,
    needsTicker: true,
  },
  {
    id: "risk_daily",
    name: "risk",
    label: "Risk (daily portfolio)",
    category: "risk",
    description: "Daily portfolio risk metrics",
    method: "GET",
    path: () => `/api/risk/daily`,
    needsTicker: false,
  },
  {
    id: "risk_refresh",
    name: "risk",
    label: "Risk (refresh)",
    category: "risk",
    description: "Recompute & persist daily risk metrics",
    method: "POST",
    path: () => `/api/risk/refresh`,
    needsTicker: false,
  },
  {
    id: "factor_weights",
    name: "ai_learning",
    label: "Factor Weights",
    category: "ai",
    description: "Regime-aware factor weights via AILearningEngine",
    method: "GET",
    path: (t) => `/api/factor-weights/${encodeURIComponent(t)}`,
    needsTicker: true,
  },
  {
    id: "ai_weights",
    name: "ai_learning",
    label: "AI Weights (trained)",
    category: "ai",
    description: "Fetch latest trained LR weights",
    method: "GET",
    path: () => `/api/ai/weights`,
    needsTicker: false,
  },
  {
    id: "ai_train",
    name: "ai_learning",
    label: "AI Train (LR)",
    category: "ai",
    description: "Train Linear Regression to optimize factor weights",
    method: "POST",
    path: () => `/api/ai/train`,
    needsTicker: false,
  },
  {
    id: "paper_trade",
    name: "paper_trading",
    label: "Paper Trade",
    category: "execution",
    description: "Simulate paper trading via PaperTradingEngine",
    method: "POST",
    path: () => `/api/paper-trade`,
    body: (t) => ({ ticker: t, capital: 100000000 }),
    needsTicker: true,
  },
  {
    id: "backtest",
    name: "backtest",
    label: "Backtest (buy&hold)",
    category: "execution",
    description: "Run buy & hold backtest via BacktestEngine",
    method: "POST",
    path: () => `/api/backtest`,
    body: (t) => ({ ticker: t, strategy: "buy_and_hold", capital: 10000000 }),
    needsTicker: true,
  },
  {
    id: "monitor",
    name: "monitoring",
    label: "System Monitor",
    category: "system",
    description: "Health check via MonitoringEngine",
    method: "GET",
    path: () => `/api/monitor`,
    needsTicker: false,
  },
  {
    id: "engines",
    name: "engines",
    label: "Engines Status",
    category: "system",
    description: "Live status of all registered engines",
    method: "GET",
    path: () => `/api/engines`,
    needsTicker: false,
  },
];

const CATEGORY_ORDER: Category[] = [
  "pipeline",
  "data",
  "analysis",
  "decision",
  "risk",
  "ai",
  "execution",
  "system",
];

const CATEGORY_LABEL: Record<Category, string> = {
  pipeline: "PIPELINE",
  data: "DATA",
  analysis: "ANALYSIS",
  decision: "DECISION",
  risk: "RISK",
  ai: "AI LEARNING",
  execution: "EXECUTION",
  system: "SYSTEM",
};

const PRESET_TICKERS = ["BBCA.JK", "TLKM.JK", "ASII.JK", "UNVR.JK", "BMRI.JK"];

// Pipeline sequence for "Run Pipeline" — ordered analysis → decision flow.
const PIPELINE_SEQUENCE = [
  "compute_scores",
  "indicators",
  "relationship",
  "sentiment",
  "recommend",
  "explain",
] as const;

// ---------------------------------------------------------------------------
// Run record model.
// ---------------------------------------------------------------------------
interface RunRecord {
  id: string;
  moduleId: string;
  moduleLabel: string;
  category: Category;
  ticker: string;
  status: "running" | "ok" | "error";
  latencyMs: number | null;
  startedAt: string;
  finishedAt: string | null;
  httpStatus: number | null;
  error: string | null;
  data: unknown;
}

// ---------------------------------------------------------------------------
// Helpers.
// ---------------------------------------------------------------------------
function nowTime() {
  return new Date().toLocaleTimeString("id-ID", { hour12: false });
}

function statusColor(s: RunRecord["status"]) {
  switch (s) {
    case "running":
      return "text-blue-400";
    case "ok":
      return "text-green-400";
    default:
      return "text-red-400";
  }
}

function statusDot(s: RunRecord["status"]) {
  switch (s) {
    case "running":
      return "bg-blue-500 animate-pulse";
    case "ok":
      return "bg-green-500";
    default:
      return "bg-red-500";
  }
}

function summarizeData(data: unknown): string {
  if (data === null || data === undefined) return "—";
  if (typeof data !== "object") return String(data);
  const obj = data as Record<string, unknown>;
  if (Array.isArray(obj.data)) return `array[${obj.data.length}]`;
  if (Array.isArray(obj.engines)) return `engines[${obj.engines.length}]`;
  if (Array.isArray(obj.metrics)) return `metrics[${obj.metrics.length}]`;
  if (Array.isArray(obj.equity_curve)) return `equity[${obj.equity_curve.length}]`;
  if (typeof obj.scores === "object" && obj.scores) {
    const keys = Object.keys(obj.scores as object);
    return `scores{${keys.length}}`;
  }
  if (typeof obj.recommendation === "object") return "recommendation";
  if (typeof obj.narrative === "string") return "explanation";
  const keys = Object.keys(obj);
  return `obj{${keys.slice(0, 4).join(",")}${keys.length > 4 ? "…" : ""}}`;
}

// ---------------------------------------------------------------------------
// Page.
// ---------------------------------------------------------------------------
export default function SimulationPage() {
  const [ticker, setTicker] = useState("BBCA.JK");
  const [tickerInput, setTickerInput] = useState("BBCA.JK");
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  const applyTicker = useCallback(() => {
    const trimmed = tickerInput.trim().toUpperCase();
    if (trimmed) setTicker(trimmed);
  }, [tickerInput]);

  // Run a single module and append a RunRecord.
  const runModule = useCallback(
    async (mod: ModuleDef, runTicker?: string): Promise<RunRecord> => {
      const t = runTicker ?? ticker;
      if (mod.needsTicker && !t) {
        const rec: RunRecord = {
          id: `${mod.id}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          moduleId: mod.id,
          moduleLabel: mod.label,
          category: mod.category,
          ticker: t,
          status: "error",
          latencyMs: null,
          startedAt: nowTime(),
          finishedAt: nowTime(),
          httpStatus: null,
          error: "Ticker required",
          data: null,
        };
        setRuns((prev) => [rec, ...prev]);
        return rec;
      }

      const id = `${mod.id}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      const startedAt = nowTime();
      const rec: RunRecord = {
        id,
        moduleId: mod.id,
        moduleLabel: mod.label,
        category: mod.category,
        ticker: t,
        status: "running",
        latencyMs: null,
        startedAt,
        finishedAt: null,
        httpStatus: null,
        error: null,
        data: null,
      };

      setRuns((prev) => [rec, ...prev]);
      setSelectedRunId(id);
      setRunningIds((prev) => new Set(prev).add(mod.id));

      const t0 = performance.now();
      try {
        const init: RequestInit = { method: mod.method };
        if (mod.method === "POST" && mod.body) {
          init.headers = { "Content-Type": "application/json" };
          init.body = JSON.stringify(mod.body(t));
        }
        const res = await apiFetch(mod.path(t), init);
        const latencyMs = Math.round(performance.now() - t0);
        const json = await res.json().catch(() => null);
        const finished: RunRecord = {
          ...rec,
          status: "ok",
          latencyMs,
          finishedAt: nowTime(),
          httpStatus: res.status,
          data: json,
        };
        setRuns((prev) => prev.map((r) => (r.id === id ? finished : r)));
        return finished;
      } catch (err) {
        const latencyMs = Math.round(performance.now() - t0);
        const msg =
          err instanceof APIError
            ? `HTTP ${err.status}: ${err.message}`
            : err instanceof Error
              ? err.message
              : "Network error";
        const finished: RunRecord = {
          ...rec,
          status: "error",
          latencyMs,
          finishedAt: nowTime(),
          httpStatus: err instanceof APIError ? err.status : null,
          error: msg,
          data: null,
        };
        setRuns((prev) => prev.map((r) => (r.id === id ? finished : r)));
        return finished;
      } finally {
        setRunningIds((prev) => {
          const next = new Set(prev);
          next.delete(mod.id);
          return next;
        });
      }
    },
    [ticker],
  );

  // Run the full pipeline sequentially.
  const runPipeline = useCallback(async () => {
    setPipelineRunning(true);
    for (const modId of PIPELINE_SEQUENCE) {
      const mod = MODULES.find((m) => m.id === modId);
      if (!mod) continue;
      await runModule(mod);
    }
    setPipelineRunning(false);
  }, [runModule]);

  const clearLog = useCallback(() => {
    setRuns([]);
    setSelectedRunId(null);
  }, []);

  // Auto-scroll the run log to top on new entries.
  useEffect(() => {
    if (autoScroll && logEndRef.current) {
      logEndRef.current.scrollIntoView({ block: "nearest" });
    }
  }, [runs, autoScroll]);

  const selectedRun = useMemo(
    () => runs.find((r) => r.id === selectedRunId) ?? null,
    [runs, selectedRunId],
  );

  const stats = useMemo(() => {
    const ok = runs.filter((r) => r.status === "ok").length;
    const err = runs.filter((r) => r.status === "error").length;
    const running = runs.filter((r) => r.status === "running").length;
    const avgLatency =
      runs.filter((r) => r.latencyMs !== null).length > 0
        ? Math.round(
          runs
            .filter((r) => r.latencyMs !== null)
            .reduce((sum, r) => sum + (r.latencyMs ?? 0), 0) /
          runs.filter((r) => r.latencyMs !== null).length,
        )
        : 0;
    return { ok, err, running, avgLatency, total: runs.length };
  }, [runs]);

  const modulesByCategory = useMemo(() => {
    const map = new Map<Category, ModuleDef[]>();
    for (const cat of CATEGORY_ORDER) {
      map.set(cat, MODULES.filter((m) => m.category === cat));
    }
    return map;
  }, []);

  return (
    <TerminalLayout active="simulation" ticker={ticker}>
      {/* Header / controls */}
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-bold tracking-tight text-zinc-100">
          SIMULATION TEST BENCH
        </h1>
        <div className="flex items-center gap-4 font-mono text-xs text-zinc-500">
          <span className="text-zinc-400">RUNS: {stats.total}</span>
          <span className="text-green-400">OK: {stats.ok}</span>
          <span className="text-red-400">ERR: {stats.err}</span>
          {stats.running > 0 && (
            <span className="text-blue-400">RUNNING: {stats.running}</span>
          )}
          <span>AVG: {stats.avgLatency} ms</span>
        </div>
      </div>

      <p className="mb-3 text-xs text-zinc-500">
        Jalankan setiap modul/engine secara langsung untuk menguji data & pipeline.
        Pilih ticker, klik kartu modul, atau jalankan urutan pipeline lengkap.
      </p>

      {/* Ticker bar */}
      <div className="mb-3 flex flex-wrap items-center gap-2 border border-zinc-800 bg-zinc-900/50 p-2">
        <span className="font-mono text-[10px] text-zinc-500">TICKER</span>
        <input
          type="text"
          value={tickerInput}
          onChange={(e) => setTickerInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") applyTicker();
          }}
          placeholder="e.g. BBCA.JK"
          className="w-32 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 font-mono text-xs text-zinc-100 focus:border-blue-500 focus:outline-none"
        />
        <button
          onClick={applyTicker}
          className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1 font-mono text-xs text-zinc-200 hover:bg-zinc-700"
        >
          SET
        </button>
        <span className="mx-1 text-zinc-700">|</span>
        {PRESET_TICKERS.map((t) => (
          <button
            key={t}
            onClick={() => {
              setTicker(t);
              setTickerInput(t);
            }}
            className={`rounded px-2 py-1 font-mono text-[10px] ${ticker === t
                ? "bg-blue-600 text-white"
                : "border border-zinc-800 text-zinc-400 hover:bg-zinc-800"
              }`}
          >
            {t}
          </button>
        ))}
        <span className="mx-1 text-zinc-700">|</span>
        <button
          onClick={runPipeline}
          disabled={pipelineRunning}
          className="rounded bg-green-700 px-3 py-1 font-mono text-xs font-bold text-white hover:bg-green-600 disabled:opacity-50"
        >
          {pipelineRunning ? "PIPELINE RUNNING…" : "RUN PIPELINE"}
        </button>
        <button
          onClick={clearLog}
          disabled={runs.length === 0}
          className="ml-auto rounded border border-zinc-700 bg-zinc-900 px-3 py-1 font-mono text-xs text-zinc-400 hover:bg-zinc-800 disabled:opacity-40"
        >
          CLEAR LOG
        </button>
      </div>

      {/* Main grid: module catalog | run log | detail */}
      <div className="grid flex-1 grid-cols-12 gap-2 overflow-hidden">
        {/* Module catalog */}
        <div className="col-span-4 flex flex-col overflow-auto border border-zinc-800 bg-zinc-900/30 p-2 xl:col-span-3">
          <div className="mb-2 font-mono text-[10px] text-zinc-500">
            MODULES ({MODULES.length})
          </div>
          <div className="space-y-3">
            {CATEGORY_ORDER.map((cat) => {
              const mods = modulesByCategory.get(cat) ?? [];
              if (mods.length === 0) return null;
              return (
                <div key={cat}>
                  <div className="mb-1 border-b border-zinc-800 pb-0.5 font-mono text-[9px] tracking-widest text-zinc-600">
                    {CATEGORY_LABEL[cat]}
                  </div>
                  <div className="space-y-1">
                    {mods.map((mod) => {
                      const isRunning = runningIds.has(mod.id);
                      const lastRun = runs.find((r) => r.moduleId === mod.id);
                      return (
                        <button
                          key={mod.id}
                          onClick={() => runModule(mod)}
                          disabled={isRunning || (mod.needsTicker && !ticker)}
                          className="group block w-full rounded border border-zinc-800 bg-zinc-900/60 p-2 text-left transition hover:border-blue-600 hover:bg-zinc-800/60 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-[11px] font-bold text-zinc-200 group-hover:text-blue-300">
                              {mod.label}
                            </span>
                            {isRunning ? (
                              <span className="text-[9px] text-blue-400">RUN…</span>
                            ) : lastRun ? (
                              <span
                                className={`text-[9px] ${statusColor(lastRun.status)}`}
                              >
                                {lastRun.status === "ok"
                                  ? `${lastRun.latencyMs}ms`
                                  : lastRun.status === "error"
                                    ? "ERR"
                                    : "…"}
                              </span>
                            ) : (
                              <span className="text-[9px] text-zinc-600">—</span>
                            )}
                          </div>
                          <div className="mt-0.5 text-[9px] leading-tight text-zinc-500">
                            {mod.description}
                          </div>
                          <div className="mt-1 flex gap-1 font-mono text-[8px] text-zinc-600">
                            <span className="rounded bg-zinc-800 px-1">
                              {mod.method}
                            </span>
                            {mod.needsTicker ? (
                              <span className="rounded bg-zinc-800 px-1">
                                ticker
                              </span>
                            ) : (
                              <span className="rounded bg-zinc-800 px-1">
                                global
                              </span>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Run log / process timeline */}
        <div className="col-span-4 flex flex-col overflow-hidden border border-zinc-800 bg-black/40 xl:col-span-5">
          <div className="flex items-center justify-between border-b border-zinc-800 p-2">
            <span className="font-mono text-[10px] text-zinc-500">
              PROCESS LOG ({runs.length})
            </span>
            <label className="flex items-center gap-1 font-mono text-[9px] text-zinc-500">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="h-3 w-3 accent-blue-500"
              />
              AUTOSCROLL
            </label>
          </div>
          <div className="flex-1 overflow-auto p-1 font-mono text-[10px]">
            {runs.length === 0 ? (
              <div className="p-4 text-zinc-600">
                Belum ada eksekusi. Klik kartu modul di kiri atau &quot;RUN
                PIPELINE&quot;.
              </div>
            ) : (
              <div>
                {runs.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => setSelectedRunId(r.id)}
                    className={`block w-full border-b border-zinc-900 px-2 py-1 text-left transition hover:bg-zinc-800/40 ${selectedRunId === r.id ? "bg-zinc-800/60" : ""
                      }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className={`h-2 w-2 rounded-full ${statusDot(r.status)}`} />
                      <span className="text-zinc-300">{r.moduleLabel}</span>
                      <span className="text-zinc-600">[{r.category}]</span>
                      {r.ticker && (
                        <span className="text-blue-400">{r.ticker}</span>
                      )}
                      <span className="ml-auto text-zinc-600">{r.startedAt}</span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-3 pl-4 text-zinc-500">
                      <span className={statusColor(r.status)}>
                        {r.status.toUpperCase()}
                      </span>
                      {r.latencyMs !== null && (
                        <span>{r.latencyMs} ms</span>
                      )}
                      {r.httpStatus !== null && (
                        <span>HTTP {r.httpStatus}</span>
                      )}
                      <span className="text-zinc-600">
                        → {summarizeData(r.data)}
                      </span>
                      {r.error && (
                        <span className="truncate text-red-400">{r.error}</span>
                      )}
                    </div>
                  </button>
                ))}
                <div ref={logEndRef} />
              </div>
            )}
          </div>
        </div>

        {/* Detail / output */}
        <div className="col-span-4 flex flex-col overflow-hidden border border-zinc-800 bg-zinc-900/30 xl:col-span-4">
          <div className="border-b border-zinc-800 p-2 font-mono text-[10px] text-zinc-500">
            DETAIL {selectedRun ? `· ${selectedRun.moduleLabel}` : "—"}
          </div>
          {selectedRun ? (
            <div className="flex flex-1 flex-col overflow-auto">
              <div className="border-b border-zinc-800 p-2 font-mono text-[10px]">
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-zinc-400">
                  <span className="text-zinc-600">MODULE</span>
                  <span className="text-zinc-200">{selectedRun.moduleLabel}</span>
                  <span className="text-zinc-600">ID</span>
                  <span className="text-zinc-200">{selectedRun.moduleId}</span>
                  <span className="text-zinc-600">CATEGORY</span>
                  <span className="text-zinc-200">{selectedRun.category}</span>
                  <span className="text-zinc-600">TICKER</span>
                  <span className="text-blue-400">
                    {selectedRun.ticker || "—"}
                  </span>
                  <span className="text-zinc-600">STATUS</span>
                  <span className={statusColor(selectedRun.status)}>
                    {selectedRun.status.toUpperCase()}
                  </span>
                  <span className="text-zinc-600">HTTP</span>
                  <span className="text-zinc-200">
                    {selectedRun.httpStatus ?? "—"}
                  </span>
                  <span className="text-zinc-600">LATENCY</span>
                  <span className="text-zinc-200">
                    {selectedRun.latencyMs !== null
                      ? `${selectedRun.latencyMs} ms`
                      : "—"}
                  </span>
                  <span className="text-zinc-600">START</span>
                  <span className="text-zinc-200">{selectedRun.startedAt}</span>
                  <span className="text-zinc-600">FINISH</span>
                  <span className="text-zinc-200">
                    {selectedRun.finishedAt ?? "—"}
                  </span>
                </div>
                {selectedRun.error && (
                  <div className="mt-2 rounded border border-red-900 bg-red-900/20 p-2 text-red-400">
                    {selectedRun.error}
                  </div>
                )}
              </div>
              <div className="flex-1 overflow-auto p-2">
                <div className="mb-1 font-mono text-[9px] text-zinc-600">
                  RAW OUTPUT (JSON)
                </div>
                <pre className="whitespace-pre-wrap break-words font-mono text-[10px] leading-relaxed text-zinc-300">
                  {selectedRun.data === null
                    ? "—"
                    : JSON.stringify(selectedRun.data, null, 2)}
                </pre>
              </div>
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center p-4 text-center font-mono text-[10px] text-zinc-600">
              Pilih entri di PROCESS LOG untuk melihat detail output engine.
            </div>
          )}
        </div>
      </div>
    </TerminalLayout>
  );
}
