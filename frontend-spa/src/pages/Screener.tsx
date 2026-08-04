import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch, safeApiFetch } from "../lib/api";

type Mode = "factors" | "technical";
type Template = "technical" | "momentum" | "value";

interface FactorRow {
  symbol: string;
  composite_rank: number;
  factor_breakdown: Record<
    string,
    { raw_value: number | null; percentile_rank: number; bars_used: number }
  >;
}

interface FactorResult {
  as_of: string;
  factor_version: string;
  universe_size: number;
  scored_instruments: number;
  screened_count: number;
  results: FactorRow[];
  skipped_liquidity: number;
  skipped_history: number;
}

interface TechnicalResult {
  template: Template;
  universe_scanned: number;
  passed: number;
  results: Record<string, number | string | null>[];
}

interface FactorExplain {
  symbol: string;
  found: boolean;
  composite_rank?: number;
  factor_version?: string;
  as_of?: string;
  factors?: {
    factor: string;
    raw_value: number | null;
    percentile_rank: number;
    tier: string;
    bars_used: number;
    explanation: string;
  }[];
}

function rankColor(pct: number): string {
  if (pct >= 0.8) return "text-green-400";
  if (pct >= 0.6) return "text-green-500/80";
  if (pct >= 0.4) return "text-zinc-300";
  if (pct >= 0.2) return "text-amber-400";
  return "text-red-400";
}

export default function Screener() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("factors");
  const [template, setTemplate] = useState<Template>("technical");
  const [topN, setTopN] = useState(20);
  const [maxTickers, setMaxTickers] = useState(300);
  const [minComposite, setMinComposite] = useState(0.0);
  const [factorFilter, setFactorFilter] = useState("");
  const [tickers, setTickers] = useState("");

  const [factorResult, setFactorResult] = useState<FactorResult | null>(null);
  const [techResult, setTechResult] = useState<TechnicalResult | null>(null);
  const [explain, setExplain] = useState<FactorExplain | null>(null);
  const [loading, setLoading] = useState(false);
  const [explaining, setExplaining] = useState<string | null>(null);
  const [error, setError] = useState("");

  const runScreen = useCallback(async () => {
    setLoading(true);
    setError("");
    setExplain(null);
    setFactorResult(null);
    setTechResult(null);
    try {
      const tickersParam = tickers.trim() ? `&tickers=${encodeURIComponent(tickers.trim())}` : "";
      if (mode === "factors") {
        const ff = factorFilter.trim()
          ? `&factor_filter=${encodeURIComponent(factorFilter.trim())}`
          : "";
        const res = await apiFetch(
          `/api/factors?top_n=${topN}&min_composite=${minComposite}${ff}${tickersParam}`,
        );
        setFactorResult((await res.json()) as FactorResult);
      } else {
        const res = await apiFetch(
          `/api/screen?template=${template}&top_n=${topN}&max_tickers=${maxTickers}${tickersParam}`,
        );
        setTechResult((await res.json()) as TechnicalResult);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Screen failed");
    } finally {
      setLoading(false);
    }
  }, [mode, template, topN, maxTickers, minComposite, factorFilter, tickers]);

  const explainTicker = useCallback(async (ticker: string) => {
    setExplaining(ticker);
    setError("");
    setExplain(null);
    const { data, error } = await safeApiFetch<FactorExplain>(`/api/factors/${ticker}`);
    if (error) setError(error.message);
    if (data) setExplain(data);
    setExplaining(null);
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-zinc-200">Stock Screener &amp; Ranking</h2>
        <span className="text-[10px] text-zinc-600">
          Universe: all IDX (.JK) tickers · {mode === "factors" ? "FactorEngine composite" : "Technical template"}
        </span>
      </div>

      {/* Controls */}
      <div className="border border-zinc-800 bg-zinc-900/50 p-3 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* Mode */}
          <div className="flex border border-zinc-700">
            {(["factors", "technical"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-3 py-1 text-xs ${
                  mode === m ? "bg-blue-900/50 text-blue-300" : "text-zinc-400 hover:bg-zinc-800"
                }`}
              >
                {m === "factors" ? "Factor Rank" : "Technical"}
              </button>
            ))}
          </div>

          {mode === "technical" && (
            <div className="flex border border-zinc-700">
              {(["technical", "momentum", "value"] as Template[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTemplate(t)}
                  className={`px-3 py-1 text-xs capitalize ${
                    template === t ? "bg-blue-900/50 text-blue-300" : "text-zinc-400 hover:bg-zinc-800"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          )}

          <label className="flex items-center gap-1 text-xs text-zinc-400">
            Top
            <input
              type="number"
              min={1}
              max={100}
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value) || 20)}
              className="w-16 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>

          {mode === "factors" ? (
            <>
              <label className="flex items-center gap-1 text-xs text-zinc-400">
                Min composite
                <input
                  type="number"
                  step={0.05}
                  min={0}
                  max={1}
                  value={minComposite}
                  onChange={(e) => setMinComposite(Number(e.target.value) || 0)}
                  className="w-20 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
                />
              </label>
              <label className="flex items-center gap-1 text-xs text-zinc-400">
                Factor filter
                <input
                  value={factorFilter}
                  onChange={(e) => setFactorFilter(e.target.value)}
                  placeholder="e.g. momentum"
                  className="w-28 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
                />
              </label>
            </>
          ) : (
            <label className="flex items-center gap-1 text-xs text-zinc-400">
              Max scan
              <input
                type="number"
                min={10}
                max={1000}
                value={maxTickers}
                onChange={(e) => setMaxTickers(Number(e.target.value) || 300)}
                className="w-20 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
              />
            </label>
          )}

          <label className="flex items-center gap-1 text-xs text-zinc-400">
            Tickers
            <input
              value={tickers}
              onChange={(e) => setTickers(e.target.value)}
              placeholder="A.JK,B.JK (optional)"
              className="w-44 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>

          <button
            onClick={runScreen}
            disabled={loading}
            className="border border-blue-700 bg-blue-900/30 px-3 py-1 text-xs text-blue-300 hover:bg-blue-900/50 disabled:opacity-50"
          >
            {loading ? "Screening..." : "Run Screen"}
          </button>
        </div>

        {error && <div className="text-xs text-red-400">{error}</div>}
      </div>

      {/* Results: Factor mode */}
      {mode === "factors" && factorResult && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="UNIVERSE" value={String(factorResult.universe_size)} />
            <Stat label="SCORED" value={String(factorResult.scored_instruments)} />
            <Stat label="RETURNED" value={String(factorResult.screened_count)} />
            <Stat
              label="SKIPPED (liq/hist)"
              value={`${factorResult.skipped_liquidity}/${factorResult.skipped_history}`}
            />
          </div>
          <div className="border border-zinc-800 bg-zinc-900/50">
            <table className="w-full text-xs">
              <thead className="bg-zinc-900/80 text-[10px] uppercase text-zinc-500">
                <tr>
                  <th className="px-2 py-1 text-left">#</th>
                  <th className="px-2 py-1 text-left">Ticker</th>
                  <th className="px-2 py-1 text-right">Composite</th>
                  <th className="px-2 py-1 text-left">Top factors (percentile)</th>
                  <th className="px-2 py-1 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {factorResult.results.map((r, i) => {
                  const fb = r.factor_breakdown || {};
                  const top = Object.entries(fb)
                    .sort((a, b) => (b[1].percentile_rank || 0) - (a[1].percentile_rank || 0))
                    .slice(0, 4);
                  return (
                    <tr key={r.symbol} className="border-t border-zinc-800/60 hover:bg-zinc-800/30">
                      <td className="px-2 py-1 text-zinc-500">{i + 1}</td>
                      <td className="px-2 py-1 font-mono text-zinc-100">{r.symbol}</td>
                      <td className={`px-2 py-1 text-right font-mono ${rankColor(r.composite_rank)}`}>
                        {r.composite_rank.toFixed(3)}
                      </td>
                      <td className="px-2 py-1 text-zinc-400">
                        {top.length ? (
                          top.map(([k, v]) => (
                            <span key={k} className="mr-2">
                              <span className="text-zinc-500">{k}</span>{" "}
                              <span className={rankColor(v.percentile_rank)}>
                                {(v.percentile_rank * 100).toFixed(0)}%
                              </span>
                            </span>
                          ))
                        ) : (
                          <span className="text-zinc-600">—</span>
                        )}
                      </td>
                      <td className="px-2 py-1 text-right">
                        <button
                          onClick={() => explainTicker(r.symbol)}
                          disabled={explaining === r.symbol}
                          className="mr-2 text-[10px] text-blue-400 hover:text-blue-300 disabled:opacity-50"
                        >
                          {explaining === r.symbol ? "..." : "Explain"}
                        </button>
                        <button
                          onClick={() => navigate(`/dashboard?ticker=${encodeURIComponent(r.symbol)}`)}
                          className="text-[10px] text-zinc-400 hover:text-zinc-200"
                        >
                          Open →
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {factorResult.results.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-2 py-4 text-center text-zinc-600">
                      No instruments passed the filter. Try lowering min composite.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Results: Technical mode */}
      {mode === "technical" && techResult && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <Stat label="UNIVERSE SCANNED" value={String(techResult.universe_scanned)} />
            <Stat label="PASSED" value={String(techResult.passed)} />
            <Stat label="TEMPLATE" value={techResult.template} />
          </div>
          <div className="border border-zinc-800 bg-zinc-900/50">
            <table className="w-full text-xs">
              <thead className="bg-zinc-900/80 text-[10px] uppercase text-zinc-500">
                <tr>
                  {techResult.results[0] &&
                    Object.keys(techResult.results[0]).map((k) => (
                      <th key={k} className="px-2 py-1 text-left">
                        {k}
                      </th>
                    ))}
                  <th className="px-2 py-1 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {techResult.results.map((row, i) => {
                  const ticker = String(row.ticker || "");
                  return (
                    <tr key={ticker + i} className="border-t border-zinc-800/60 hover:bg-zinc-800/30">
                      {Object.keys(techResult.results[0] || {}).map((k) => {
                        const v = row[k];
                        const isScore = k === "score" || k === "composite";
                        return (
                          <td
                            key={k}
                            className={`px-2 py-1 font-mono ${
                              k === "ticker" ? "text-zinc-100" : isScore ? "text-green-400" : "text-zinc-300"
                            }`}
                          >
                            {v === null || v === undefined
                              ? "—"
                              : typeof v === "number"
                                ? Number.isInteger(v)
                                  ? v.toLocaleString()
                                  : v.toFixed(2)
                                : String(v)}
                          </td>
                        );
                      })}
                      <td className="px-2 py-1 text-right">
                        <button
                          onClick={() => navigate(`/dashboard?ticker=${encodeURIComponent(ticker)}`)}
                          className="text-[10px] text-zinc-400 hover:text-zinc-200"
                        >
                          Open →
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {techResult.results.length === 0 && (
                  <tr>
                    <td colSpan={10} className="px-2 py-4 text-center text-zinc-600">
                      No tickers passed this template. Try a different template or raise max scan.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Factor explain panel */}
      {explain && (
        <div className="border border-zinc-800 bg-zinc-900/50 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-zinc-200">
              Factor Breakdown — {explain.symbol}
              {explain.composite_rank !== undefined && (
                <span className={`ml-2 font-mono ${rankColor(explain.composite_rank)}`}>
                  composite {explain.composite_rank.toFixed(3)}
                </span>
              )}
            </h3>
            <button onClick={() => setExplain(null)} className="text-[10px] text-zinc-500 hover:text-zinc-200">
              close
            </button>
          </div>
          {explain.factors && explain.factors.length > 0 ? (
            <div className="space-y-1">
              {explain.factors
                .sort((a, b) => b.percentile_rank - a.percentile_rank)
                .map((f) => (
                  <div key={f.factor} className="flex items-center gap-3 text-xs">
                    <span className="w-32 text-zinc-400">{f.factor}</span>
                    <div className="flex-1">
                      <div className="h-1.5 w-full bg-zinc-800">
                        <div
                          className={`h-full ${rankColor(f.percentile_rank).replace("text-", "bg-")}`}
                          style={{ width: `${f.percentile_rank * 100}%` }}
                        />
                      </div>
                    </div>
                    <span className={`w-12 text-right font-mono ${rankColor(f.percentile_rank)}`}>
                      {(f.percentile_rank * 100).toFixed(0)}%
                    </span>
                    <span className="w-28 text-[10px] text-zinc-500">{f.tier}</span>
                  </div>
                ))}
            </div>
          ) : (
            <div className="text-xs text-zinc-600">No factor data available for this ticker.</div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="text-[10px] text-zinc-500">{label}</div>
      <div className="text-lg font-mono text-zinc-100">{value}</div>
    </div>
  );
}
