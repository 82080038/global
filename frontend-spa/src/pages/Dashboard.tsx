import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiFetch, safeApiFetch } from "../lib/api";

interface MonitorData {
  status: string;
  tickers_in_db: string[];
  score_count: number;
  alerts: { source: string; status: string; last_error: string }[];
  sources: { source: string; status: string; last_success: string; last_error: string }[];
}

interface MarketStatus {
  is_open: boolean;
  next_open: string | null;
  next_close: string | null;
  recommended_actions: string[];
}

interface OHLCVRow {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  rsi?: number;
  ma_20?: number;
  ma_50?: number;
}

interface ScoreItem {
  engine: string;
  score: number;
}

interface Recommendation {
  action: string;
  conviction: number;
  entry_low: number;
  entry_high: number;
  rationale: string;
}

interface Explanation {
  narrative: string;
  top_factors: { factor: string; contribution: number; direction: string }[];
}

interface TopPick {
  symbol: string;
  composite_rank: number;
  factor_breakdown: Record<string, { percentile_rank: number }>;
}

interface TopPicksResult {
  universe_size: number;
  scored_instruments: number;
  screened_count: number;
  results: TopPick[];
}

export default function Dashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTicker = searchParams.get("ticker") || "BBCA.JK";
  const [ticker, setTicker] = useState(initialTicker);
  const [tickerInput, setTickerInput] = useState(initialTicker);
  const [monitor, setMonitor] = useState<MonitorData | null>(null);
  const [marketStatus, setMarketStatus] = useState<MarketStatus | null>(null);
  const [ohlcv, setOhlcv] = useState<OHLCVRow[]>([]);
  const [scores, setScores] = useState<ScoreItem[]>([]);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState("");
  const [tickerSearch, setTickerSearch] = useState("");
  const [topPicks, setTopPicks] = useState<TopPick[]>([]);
  const [topPicksLoading, setTopPicksLoading] = useState(false);

  // --- Light data: monitor + market status (fast, <1s) ---
  const fetchSummary = useCallback(async () => {
    const [monRes, mkRes] = await Promise.all([
      safeApiFetch<MonitorData>("/api/monitor"),
      safeApiFetch<MarketStatus>("/api/market-status"),
    ]);
    if (monRes.data) setMonitor(monRes.data);
    if (mkRes.data) setMarketStatus(mkRes.data);
  }, []);

  // --- Top picks: factor-screened universe ranking (best trading candidates) ---
  // max_tickers caps the scan so the dashboard loads fast (~2-3s, not ~18s).
  const fetchTopPicks = useCallback(async () => {
    setTopPicksLoading(true);
    const { data } = await safeApiFetch<TopPicksResult>(
      "/api/factors?top_n=10&min_composite=0.4&max_tickers=120",
    );
    if (data?.results) setTopPicks(data.results);
    setTopPicksLoading(false);
  }, []);

  // Wrapper untuk setTicker yang juga sync ke URL query param.
  const selectTicker = useCallback(
    (t: string) => {
      setTicker(t);
      setTickerInput(t);
      setSearchParams({ ticker: t }, { replace: true });
    },
    [setSearchParams],
  );

  // --- OHLCV + scores (medium, ~0.6s) ---
  const fetchTickerData = useCallback(async (t: string) => {
    setLoading(true);
    setError("");
    try {
      const [ohlcvRes, scoresRes] = await Promise.all([
        apiFetch(`/api/indicators/${t}?limit=200`),
        apiFetch(`/api/scores/${t}`),
      ]);
      const ohlcvJson = await ohlcvRes.json();
      const scoresJson = await scoresRes.json();
      setOhlcv(
        (ohlcvJson.data || []).map((row: Record<string, unknown>) => ({
          time: row.time as string,
          open: row.open as number,
          high: row.high as number,
          low: row.low as number,
          close: row.close as number,
          volume: (row.volume as number) ?? 0,
          rsi: row.rsi as number | undefined,
          ma_20: row.ma_20 as number | undefined,
          ma_50: row.ma_50 as number | undefined,
        })),
      );
      setScores(
        Object.entries(scoresJson.scores || {}).map(([engine, score]) => ({
          engine,
          score: Number(score),
        })),
      );
      setLastUpdated(new Date().toLocaleString("id-ID"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch data");
    } finally {
      setLoading(false);
    }
  }, []);

  // --- Heavy data: recommend + explain (slow, ~60s) — only on demand ---
  const runAnalysis = useCallback(async () => {
    setAnalyzing(true);
    try {
      const [recRes, expRes] = await Promise.all([
        apiFetch(`/api/recommend/${ticker}`),
        apiFetch(`/api/explain/${ticker}`),
      ]);
      const recJson = await recRes.json();
      const expJson = await expRes.json();
      setRecommendation(recJson.recommendation || null);
      setExplanation(expJson || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }, [ticker]);

  // Initial load: summary + ticker data + top picks (no heavy analysis)
  useEffect(() => {
    fetchSummary();
    fetchTickerData(ticker);
    fetchTopPicks();
    const summaryInterval = setInterval(fetchSummary, 30000);
    return () => clearInterval(summaryInterval);
  }, [fetchSummary, fetchTickerData, fetchTopPicks, ticker]);

  const filteredTickers = useMemo(() => {
    const all = monitor?.tickers_in_db || [];
    if (!tickerSearch) return all.slice(0, 50);
    return all.filter((t) => t.toLowerCase().includes(tickerSearch.toLowerCase())).slice(0, 50);
  }, [monitor, tickerSearch]);

  const latestData = ohlcv[ohlcv.length - 1];
  const prevData = ohlcv[ohlcv.length - 2];
  const priceChange = latestData && prevData ? latestData.close - prevData.close : 0;
  const priceChangePct = latestData && prevData ? ((priceChange / prevData.close) * 100).toFixed(2) : "0.00";

  const isClosed = marketStatus && !marketStatus.is_open;

  return (
    <div className="space-y-4">
      {/* Market Status Banner */}
      {marketStatus && (
        <div
          className={`border p-3 text-xs ${
            marketStatus.is_open ? "border-green-800/50 bg-green-950/20" : "border-zinc-800 bg-zinc-900/30"
          }`}
        >
          <div className="flex items-center gap-3">
            <span
              className={`font-bold ${
                marketStatus.is_open ? "text-green-400" : "text-zinc-400"
              }`}
            >
              {marketStatus.is_open ? "MARKET OPEN" : "MARKET CLOSED"}
            </span>
            {marketStatus.next_open && !marketStatus.is_open && (
              <span className="text-zinc-500">
                Next open: {new Date(marketStatus.next_open).toLocaleString("id-ID")}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Top Picks — universe ranking (best trading candidates) */}
      <div className="border border-zinc-800 bg-zinc-900/50 p-3">
        <div className="mb-2 flex items-center gap-2">
          <span className="text-[10px] text-zinc-500">TOP PICKS — factor-ranked universe</span>
          <span className="text-[10px] text-zinc-600">
            (composite rank ≥ 0.4 · click to load)
          </span>
          <button
            onClick={fetchTopPicks}
            disabled={topPicksLoading}
            className="ml-auto text-[10px] text-zinc-400 hover:text-zinc-200 disabled:opacity-50"
          >
            {topPicksLoading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        {topPicksLoading && topPicks.length === 0 ? (
          <div className="text-xs text-zinc-600">Loading ranking...</div>
        ) : topPicks.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {topPicks.map((p, i) => {
              const top = Object.entries(p.factor_breakdown || {})
                .sort((a, b) => (b[1].percentile_rank || 0) - (a[1].percentile_rank || 0))
                .slice(0, 2);
              return (
                <button
                  key={p.symbol}
                  onClick={() => selectTicker(p.symbol)}
                  title={top.map(([k, v]) => `${k}: ${(v.percentile_rank * 100).toFixed(0)}%`).join(", ")}
                  className={`flex items-center gap-1.5 border px-2 py-1 text-[10px] hover:bg-zinc-700 ${
                    p.symbol === ticker
                      ? "border-blue-500 bg-blue-900/30 text-blue-300"
                      : "border-zinc-700 bg-zinc-800 text-zinc-300"
                  }`}
                >
                  <span className="text-zinc-500">#{i + 1}</span>
                  <span className="font-mono">{p.symbol}</span>
                  <span
                    className={`font-mono ${
                      p.composite_rank >= 0.7
                        ? "text-green-400"
                        : p.composite_rank >= 0.5
                          ? "text-green-500/80"
                          : "text-zinc-400"
                    }`}
                  >
                    {p.composite_rank.toFixed(2)}
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="text-xs text-zinc-600">
            No picks yet. Run the{" "}
            <a href="/screener" className="text-blue-400 hover:underline">
              Screener
            </a>{" "}
            or refresh.
          </div>
        )}
      </div>

      {/* Ticker selector */}
      <div className="flex items-center gap-2">
        <input
          value={tickerInput}
          onChange={(e) => setTickerInput(e.target.value.toUpperCase())}
          onKeyDown={(e) => {
            if (e.key === "Enter" && tickerInput.trim()) {
              selectTicker(tickerInput.trim());
            }
          }}
          placeholder="Enter ticker..."
          className="border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
        />
        <button
          onClick={() => tickerInput.trim() && selectTicker(tickerInput.trim())}
          className="border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
        >
          Load
        </button>
        <button
          onClick={runAnalysis}
          disabled={analyzing}
          className="border border-blue-700 bg-blue-900/30 px-3 py-1 text-xs text-blue-300 hover:bg-blue-900/50 disabled:opacity-50"
        >
          {analyzing ? "Analyzing..." : "Run Analysis"}
        </button>
        {lastUpdated && <span className="ml-auto text-[10px] text-zinc-600">Updated: {lastUpdated}</span>}
      </div>

      {/* Summary grid */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {/* Price card */}
        <div className="border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="text-[10px] text-zinc-500">LAST PRICE</div>
          {loading ? (
            <div className="text-zinc-600">Loading...</div>
          ) : latestData ? (
            <>
              <div className="text-lg font-mono text-zinc-100">{latestData.close.toLocaleString()}</div>
              <div
                className={`text-xs ${priceChange >= 0 ? "text-green-400" : "text-red-400"}`}
              >
                {priceChange >= 0 ? "+" : ""}
                {priceChange.toFixed(0)} ({priceChangePct}%)
              </div>
            </>
          ) : (
            <div className="text-zinc-600">No data</div>
          )}
        </div>

        {/* Volume card */}
        <div className="border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="text-[10px] text-zinc-500">VOLUME</div>
          {latestData ? (
            <>
              <div className="text-lg font-mono text-zinc-100">
                {(latestData.volume / 1e6).toFixed(1)}M
              </div>
              <div className="text-xs text-zinc-500">{latestData.time.split("T")[0]}</div>
            </>
          ) : (
            <div className="text-zinc-600">—</div>
          )}
        </div>

        {/* Tickers count */}
        <div className="border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="text-[10px] text-zinc-500">TICKERS</div>
          <div className="text-lg font-mono text-zinc-100">
            {monitor?.tickers_in_db?.length || 0}
          </div>
          <div className="text-xs text-zinc-500">IDX equities</div>
        </div>

        {/* Scores count */}
        <div className="border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="text-[10px] text-zinc-500">SCORES</div>
          <div className="text-lg font-mono text-zinc-100">
            {monitor?.score_count || 0}
          </div>
          <div className="text-xs text-zinc-500">computed</div>
        </div>
      </div>

      {/* Scores bar */}
      {scores.length > 0 && (
        <div className="border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="mb-2 text-[10px] text-zinc-500">FACTOR SCORES — {ticker}</div>
          <div className="flex flex-wrap gap-2">
            {scores.map((s) => (
              <div key={s.engine} className="flex items-center gap-1">
                <span className="text-[10px] text-zinc-400">{s.engine}</span>
                <div className="h-2 w-16 bg-zinc-800">
                  <div
                    className={`h-full ${
                      s.score >= 60 ? "bg-green-500" : s.score >= 40 ? "bg-yellow-500" : "bg-red-500"
                    }`}
                    style={{ width: `${Math.min(s.score, 100)}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-zinc-300">{s.score.toFixed(0)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Price chart (lightweight SVG) */}
      {ohlcv.length > 0 && (
        <div className="border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="mb-2 text-[10px] text-zinc-500">
            PRICE CHART — {ticker} ({ohlcv.length} bars)
          </div>
          <MiniChart data={ohlcv} />
        </div>
      )}

      {/* Analysis results (only after clicking "Run Analysis") */}
      {(recommendation || explanation) && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {recommendation && (
            <div className="border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="mb-2 text-[10px] text-zinc-500">RECOMMENDATION</div>
              <div className="flex items-center gap-3">
                <span
                  className={`text-lg font-bold ${
                    recommendation.action === "BUY"
                      ? "text-green-400"
                      : recommendation.action === "SELL"
                        ? "text-red-400"
                        : "text-yellow-400"
                  }`}
                >
                  {recommendation.action}
                </span>
                <span className="text-xs text-zinc-400">
                  Conviction: {recommendation.conviction.toFixed(1)}
                </span>
              </div>
              {recommendation.entry_low > 0 && (
                <div className="mt-1 text-xs text-zinc-500">
                  Entry: {recommendation.entry_low.toLocaleString()} –{" "}
                  {recommendation.entry_high.toLocaleString()}
                </div>
              )}
              {recommendation.rationale && (
                <div className="mt-2 text-xs text-zinc-400">{recommendation.rationale}</div>
              )}
            </div>
          )}
          {explanation && (
            <div className="border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="mb-2 text-[10px] text-zinc-500">XAI EXPLANATION</div>
              {explanation.narrative && (
                <div className="text-xs text-zinc-400">{explanation.narrative}</div>
              )}
              {explanation.top_factors && explanation.top_factors.length > 0 && (
                <div className="mt-2 space-y-1">
                  {explanation.top_factors.slice(0, 5).map((f, i) => (
                    <div key={i} className="flex items-center gap-2 text-[10px]">
                      <span
                        className={`font-mono ${
                          f.direction === "bullish" ? "text-green-400" : "text-red-400"
                        }`}
                      >
                        {f.direction === "bullish" ? "+" : "-"}
                        {Math.abs(f.contribution).toFixed(1)}
                      </span>
                      <span className="text-zinc-400">{f.factor}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* System health */}
      {monitor && (
        <div className="border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="mb-2 text-[10px] text-zinc-500">SYSTEM HEALTH</div>
          <div className="flex flex-wrap gap-3 text-xs">
            <span className="text-zinc-400">
              Status:{" "}
              <span className={monitor.status === "ok" ? "text-green-400" : "text-red-400"}>
                {monitor.status}
              </span>
            </span>
            <span className="text-zinc-400">
              Alerts: <span className="text-zinc-200">{monitor.alerts?.length || 0}</span>
            </span>
            {monitor.sources?.slice(0, 5).map((s) => (
              <span key={s.source} className="text-zinc-400">
                {s.source}:{" "}
                <span className={s.status === "ok" ? "text-green-400" : "text-red-400"}>
                  {s.status}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Ticker list with search */}
      {monitor?.tickers_in_db && monitor.tickers_in_db.length > 0 && (
        <div className="border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[10px] text-zinc-500">Available tickers</span>
            <span className="text-[10px] text-zinc-600">
              ({monitor.tickers_in_db.length} IDX equities)
            </span>
            <input
              value={tickerSearch}
              onChange={(e) => setTickerSearch(e.target.value)}
              placeholder="Search..."
              className="ml-auto border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-100 outline-none focus:border-blue-500"
            />
          </div>
          <div className="flex max-h-32 flex-wrap gap-1 overflow-y-auto">
            {filteredTickers.map((t) => (
              <button
                key={t}
                onClick={() => selectTicker(t)}
                className={`border px-2 py-0.5 text-[10px] hover:bg-zinc-700 ${
                  t === ticker
                    ? "border-blue-500 bg-blue-900/30 text-blue-300"
                    : "border-zinc-700 bg-zinc-800 text-zinc-300"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="border border-red-800 bg-red-950/20 p-2 text-xs text-red-400">{error}</div>
      )}
    </div>
  );
}

// --- Lightweight SVG chart (no heavy charting library needed) ---
function MiniChart({ data }: { data: OHLCVRow[] }) {
  const w = 800;
  const h = 200;
  const padding = 20;
  const chartW = w - padding * 2;
  const chartH = h - padding * 2;

  const closes = data.map((d) => d.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;

  const points = data.map((d, i) => {
    const x = padding + (i / (data.length - 1)) * chartW;
    const y = padding + chartH - ((d.close - min) / range) * chartH;
    return `${x},${y}`;
  });

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ maxWidth: "100%" }}>
      {/* Grid lines */}
      {[0, 0.25, 0.5, 0.75, 1].map((p) => (
        <line
          key={p}
          x1={padding}
          y1={padding + p * chartH}
          x2={w - padding}
          y2={padding + p * chartH}
          stroke="#27272a"
          strokeWidth="0.5"
        />
      ))}
      {/* Price line */}
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke="#3b82f6"
        strokeWidth="1.5"
      />
      {/* Min/max labels */}
      <text x={padding} y={padding - 5} fill="#71717a" fontSize="10" fontFamily="monospace">
        {max.toLocaleString()}
      </text>
      <text x={padding} y={h - padding + 15} fill="#71717a" fontSize="10" fontFamily="monospace">
        {min.toLocaleString()}
      </text>
    </svg>
  );
}
