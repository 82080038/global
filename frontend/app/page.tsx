"use client";

import { useCallback, useEffect, useState } from "react";
import TerminalLayout from "./components/TerminalLayout";
import { safeApiFetch } from "./lib/api";

// ---------- Types ----------
interface DataOverview {
  tickers: { total: number; active: number; delisted: number; by_asset_class: Record<string, number> };
  sectors: { sector: string; count: number }[];
  table_counts: Record<string, number>;
  data_freshness: Record<string, number>;
  date_range: { first: string; last: string };
  stale_tickers: { ticker: string; last_date: string; rows: number; source: string; last_fetch: string }[];
}

interface MarketStatus {
  is_open: boolean;
  is_trading_day: boolean;
  is_half_day: boolean;
  holiday_name: string | null;
  current_time_wib: string;
  open_time: string;
  close_time: string;
  next_open: string | null;
  session: string;
  mode: string;
  exchange: string;
}

interface MonitorHealth {
  status: string;
  timestamp: string;
  sources: { source: string; status: string; last_success: string | null; last_error: string | null }[];
  tickers_in_db: string[];
  score_count: number;
  alerts: { source: string; status: string; last_error: string | null }[];
}

interface SourceHealth {
  source: string;
  last_success: string | null;
  last_error: string | null;
  status: string;
}

interface StorageInfo {
  database: {
    path: string;
    size_bytes: number;
    size_human: string;
    journal_mode: string;
    page_size: number;
    page_count: number;
  };
  parquet: {
    raw_dir: string;
    raw_exists: boolean;
    raw_files: number;
    raw_size_bytes: number;
    raw_size_human: string;
    archive_dir: string;
    archive_exists: boolean;
    archive_files: number;
    archive_size_bytes: number;
    archive_size_human: string;
    synced: boolean;
  };
  render: {
    total_renders: number;
    ok: number;
    failed: number;
    last_render: string | null;
    tables: { table: string; count: number; last_rendered: string | null }[];
    next_trading_day: string | null;
    today_is_trading_day: boolean | null;
    today_holiday: string | null;
    daily_runner_time: string;
    daily_runner_once: boolean;
    recommendations: string[];
  };
}

interface InstrumentStatus {
  summary: {
    total_instruments: number;
    equity_total: number;
    equity_active: number;
    equity_delisted: number;
    equity_active_with_ohlcv: number;
    equity_active_without_ohlcv: number;
    equity_delisted_with_ohlcv: number;
    non_equity_total: number;
    non_equity_with_ohlcv: number;
    non_equity_without_ohlcv: number;
  };
  active_equity: { ticker: string; name: string; sector: string; exchange: string; listing_date: string; board: string; asset_class: string }[];
  delisted_equity: { ticker: string; name: string; sector: string; exchange: string; listing_date: string; delisting_date: string; board: string; asset_class: string }[];
  equity_without_data: { ticker: string; name: string }[];
  non_equity: { ticker: string; name: string; asset_class: string; exchange: string; is_active: boolean }[];
  non_equity_without_data: { ticker: string; name: string; asset_class: string }[];
}

// ---------- Data Factor Definitions ----------
// These are all the factors that influence Indonesian stock prices
const DATA_FACTORS = [
  { key: "ohlcv", label: "OHLCV Price Data", desc: "Historical open/high/low/close/volume", category: "price" },
  { key: "technical_indicators", label: "Technical Indicators", desc: "RSI, MACD, MA, Bollinger Bands", category: "technical" },
  { key: "fundamental_data", label: "Fundamental Data", desc: "Financial statements, ratios, earnings", category: "fundamental" },
  { key: "macro_data", label: "Macro Economic", desc: "Interest rates, inflation, GDP, IHSG", category: "macro" },
  { key: "foreign_flow", label: "Foreign Capital Flow", desc: "Foreign net buy/sell per ticker", category: "flow" },
  { key: "broker_flow", label: "Broker Summary", desc: "Broker-level transaction summary", category: "flow" },
  { key: "corporate_actions", label: "Corporate Actions", desc: "Stock splits, rights issues", category: "corporate" },
  { key: "dividends", label: "Dividends", desc: "Dividend history and yields", category: "corporate" },
  { key: "news", label: "News & Sentiment", desc: "Market news and sentiment scores", category: "sentiment" },
  { key: "pattern_analysis", label: "Pattern Analysis", desc: "Chart pattern recognition results", category: "technical" },
  { key: "relationship_matrix", label: "Relationship Matrix", desc: "Cross-ticker correlations", category: "relationship" },
  { key: "stock_personality", label: "Stock Personality", desc: "Behavioral classification per ticker", category: "relationship" },
  { key: "fear_greed", label: "Fear & Greed Index", desc: "Market sentiment indicator", category: "sentiment" },
  { key: "esg_scores", label: "ESG Scores", desc: "Environmental, Social, Governance", category: "fundamental" },
  { key: "external_events", label: "External Events", desc: "Global events affecting IDX", category: "macro" },
  { key: "policy_events", label: "Policy Events", desc: "Government policy changes", category: "macro" },
  { key: "market_calendar", label: "Market Calendar", desc: "Trading days, holidays, half-days", category: "system" },
  { key: "scores", label: "Composite Scores", desc: "Multi-factor decision scores", category: "system" },
  { key: "instrument_master", label: "Instrument Master", desc: "Ticker metadata (active/delisted)", category: "system" },
  { key: "watchlist", label: "Watchlist", desc: "Tracked tickers", category: "system" },
  { key: "audit_log", label: "Audit Log", desc: "System event trail", category: "system" },
  { key: "data_watermark", label: "Data Watermark", desc: "Fetch tracking & freshness", category: "system" },
];

const CATEGORY_COLORS: Record<string, string> = {
  price: "text-blue-400 border-blue-500/30",
  technical: "text-cyan-400 border-cyan-500/30",
  fundamental: "text-green-400 border-green-500/30",
  macro: "text-amber-400 border-amber-500/30",
  flow: "text-purple-400 border-purple-500/30",
  corporate: "text-orange-400 border-orange-500/30",
  sentiment: "text-pink-400 border-pink-500/30",
  relationship: "text-indigo-400 border-indigo-500/30",
  system: "text-zinc-400 border-zinc-500/30",
};

const CATEGORY_LABELS: Record<string, string> = {
  price: "Price Data",
  technical: "Technical Analysis",
  fundamental: "Fundamental Analysis",
  macro: "Macro & Global",
  flow: "Capital Flow",
  corporate: "Corporate Actions",
  sentiment: "Sentiment",
  relationship: "Relationships",
  system: "System",
};

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatDateTime(s: string | null): string {
  if (!s) return "—";
  try {
    const d = new Date(s);
    return d.toLocaleString("id-ID", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return s;
  }
}

function completenessStatus(rows: number): { label: string; color: string; pct: number } {
  if (rows === 0) return { label: "EMPTY", color: "text-red-400 bg-red-500/10 border-red-500/30", pct: 0 };
  if (rows < 100) return { label: "SPARSE", color: "text-orange-400 bg-orange-500/10 border-orange-500/30", pct: 25 };
  if (rows < 1000) return { label: "PARTIAL", color: "text-yellow-400 bg-yellow-500/10 border-yellow-500/30", pct: 50 };
  if (rows < 10000) return { label: "GOOD", color: "text-cyan-400 bg-cyan-500/10 border-cyan-500/30", pct: 75 };
  return { label: "COMPLETE", color: "text-green-400 bg-green-500/10 border-green-500/30", pct: 100 };
}

export default function DataInspectionPage() {
  const [overview, setOverview] = useState<DataOverview | null>(null);
  const [marketStatus, setMarketStatus] = useState<MarketStatus | null>(null);
  const [monitor, setMonitor] = useState<MonitorHealth | null>(null);
  const [sourceHealth, setSourceHealth] = useState<SourceHealth[]>([]);
  const [storageInfo, setStorageInfo] = useState<StorageInfo | null>(null);
  const [instrumentStatus, setInstrumentStatus] = useState<InstrumentStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string>("");

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ovRes, msRes, monRes, hlRes, siRes, isRes] = await Promise.all([
        safeApiFetch<DataOverview>("/api/data-overview"),
        safeApiFetch<MarketStatus>("/api/market-status"),
        safeApiFetch<MonitorHealth>("/api/monitor"),
        safeApiFetch<SourceHealth[]>("/api/health"),
        safeApiFetch<StorageInfo>("/api/storage-info"),
        safeApiFetch<InstrumentStatus>("/api/instrument-status"),
      ]);

      if (ovRes.error) throw ovRes.error;
      if (msRes.error) throw msRes.error;
      if (monRes.error) throw monRes.error;
      if (hlRes.error) throw hlRes.error;
      if (siRes.error) throw siRes.error;
      if (isRes.error) throw isRes.error;

      setOverview(ovRes.data);
      setMarketStatus(msRes.data);
      setMonitor(monRes.data);
      setSourceHealth(hlRes.data || []);
      setStorageInfo(siRes.data);
      setInstrumentStatus(isRes.data);
      setLastUpdate(new Date().toLocaleString("id-ID"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data inspection");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // Group factors by category
  const factorsByCategory = DATA_FACTORS.reduce<Record<string, typeof DATA_FACTORS>>((acc, f) => {
    if (!acc[f.category]) acc[f.category] = [];
    acc[f.category].push(f);
    return acc;
  }, {});

  const totalRows = overview
    ? Object.values(overview.table_counts).reduce((a, b) => a + b, 0)
    : 0;
  const nonEmptyTables = overview
    ? Object.values(overview.table_counts).filter((c) => c > 0).length
    : 0;
  const emptyTables = DATA_FACTORS.length - nonEmptyTables;
  const overallPct = overview ? Math.round((nonEmptyTables / DATA_FACTORS.length) * 100) : 0;

  const freshnessCurrent = overview?.data_freshness?.current ?? 0;
  const freshnessStale = (overview?.data_freshness?.stale_7d ?? 0) + (overview?.data_freshness?.stale_30d ?? 0) + (overview?.data_freshness?.very_stale ?? 0);

  return (
    <TerminalLayout active="home" ticker="DATA INSPECTION">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="mb-1 text-xl font-bold tracking-tight text-zinc-100">
            DATA INSPECTION
          </h1>
          <p className="text-xs text-zinc-500">
            Pemeriksaan kelengkapan data seluruh faktor yang memengaruhi harga saham Indonesia (IDX)
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdate && (
            <span className="font-mono text-[10px] text-zinc-500">Updated: {lastUpdate}</span>
          )}
          <button
            onClick={fetchAll}
            disabled={loading}
            className="rounded bg-zinc-800 px-4 py-1 text-xs font-bold text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>

      {loading && !overview && (
        <div className="flex items-center justify-center py-20 text-sm text-zinc-500">
          Memeriksa seluruh sumber data...
        </div>
      )}

      {error && (
        <div className="mb-4 rounded border border-red-800 bg-red-900/30 p-3 text-xs text-red-400">
          {error}
        </div>
      )}

      {overview && (
        <>
          {/* ---------- Top Stats Row ---------- */}
          <div id="section-top-stats" className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <StatCard
              label="Total Tickers"
              value={overview.tickers.total.toString()}
              sub={`${overview.tickers.active} active / ${overview.tickers.delisted} delisted`}
              color="text-blue-400"
            />
            <StatCard
              label="Total Rows"
              value={formatNumber(totalRows)}
              sub={`${nonEmptyTables}/${DATA_FACTORS.length} tables populated`}
              color="text-green-400"
            />
            <StatCard
              label="Data Completeness"
              value={`${overallPct}%`}
              sub={emptyTables > 0 ? `${emptyTables} empty tables` : "All tables have data"}
              color={overallPct >= 80 ? "text-green-400" : overallPct >= 50 ? "text-yellow-400" : "text-red-400"}
            />
            <StatCard
              label="Data Freshness"
              value={`${freshnessCurrent} current`}
              sub={freshnessStale > 0 ? `${freshnessStale} stale tickers` : "All up to date"}
              color={freshnessStale > 10 ? "text-orange-400" : "text-green-400"}
            />
            <StatCard
              label="Date Range"
              value={overview.date_range.last?.slice(0, 10) ?? "—"}
              sub={`from ${overview.date_range.first?.slice(0, 10) ?? "—"}`}
              color="text-cyan-400"
            />
            <StatCard
              label="Scores Computed"
              value={formatNumber(overview.table_counts.scores ?? 0)}
              sub={`${overview.table_counts.technical_indicators ?? 0} technical rows`}
              color="text-purple-400"
            />
          </div>

          {/* ---------- Market Status ---------- */}
          {marketStatus && (
            <div id="section-market-status" className="mb-4 rounded border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-bold text-zinc-300">Market Status (IDX)</h2>
                <span className={`rounded border px-2 py-0.5 text-[10px] font-bold ${
                  marketStatus.is_open
                    ? "border-green-500/30 bg-green-500/10 text-green-400"
                    : marketStatus.is_trading_day
                      ? "border-yellow-500/30 bg-yellow-500/10 text-yellow-400"
                      : "border-red-500/30 bg-red-500/10 text-red-400"
                }`}>
                  {marketStatus.session.toUpperCase()}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4 lg:grid-cols-6">
                <div>
                  <span className="text-zinc-500">Mode</span>
                  <div className="font-mono text-zinc-200">{marketStatus.mode}</div>
                </div>
                <div>
                  <span className="text-zinc-500">Trading Day</span>
                  <div className="font-mono text-zinc-200">{marketStatus.is_trading_day ? "Yes" : "No"}</div>
                </div>
                <div>
                  <span className="text-zinc-500">Open Time</span>
                  <div className="font-mono text-zinc-200">{marketStatus.open_time} WIB</div>
                </div>
                <div>
                  <span className="text-zinc-500">Close Time</span>
                  <div className="font-mono text-zinc-200">{marketStatus.close_time} WIB</div>
                </div>
                <div>
                  <span className="text-zinc-500">Current WIB</span>
                  <div className="font-mono text-zinc-200">{marketStatus.current_time_wib?.slice(11, 19) ?? "—"}</div>
                </div>
                <div>
                  <span className="text-zinc-500">Next Open</span>
                  <div className="font-mono text-zinc-200">{marketStatus.next_open ?? "—"}</div>
                </div>
              </div>
              {marketStatus.holiday_name && (
                <div className="mt-2 text-xs text-amber-400">
                  Holiday: {marketStatus.holiday_name}
                </div>
              )}
            </div>
          )}

          {/* ---------- Listed vs Delisted Instruments ---------- */}
          {instrumentStatus && (
            <div id="section-instrument-status" className="mb-4 rounded border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-bold text-zinc-300">Instrument Status: Saham vs Non-Saham</h2>
                <div className="flex items-center gap-2">
                  <span className="rounded border border-green-500/30 bg-green-500/10 px-2 py-0.5 text-[10px] font-bold text-green-400">
                    {instrumentStatus.summary.equity_active} SAHAM LISTED
                  </span>
                  <span className="rounded border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-[10px] font-bold text-red-400">
                    {instrumentStatus.summary.equity_delisted} DELISTED
                  </span>
                  <span className="rounded border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 text-[10px] font-bold text-blue-400">
                    {instrumentStatus.summary.non_equity_total} REFERENCE
                  </span>
                </div>
              </div>

              {/* Equity summary cards */}
              <div className="mb-2 text-[10px] font-bold text-green-400">EQUITY STOCKS (SAHAM IDX)</div>
              <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                <div className="rounded border border-zinc-800 bg-zinc-900/30 p-2">
                  <div className="text-[10px] text-zinc-500">Total Saham</div>
                  <div className="font-mono text-base text-zinc-200">{instrumentStatus.summary.equity_total}</div>
                </div>
                <div className="rounded border border-zinc-800 bg-zinc-900/30 p-2">
                  <div className="text-[10px] text-zinc-500">Active (Listed)</div>
                  <div className="font-mono text-base text-green-400">{instrumentStatus.summary.equity_active}</div>
                </div>
                <div className="rounded border border-zinc-800 bg-zinc-900/30 p-2">
                  <div className="text-[10px] text-zinc-500">Delisted</div>
                  <div className="font-mono text-base text-red-400">{instrumentStatus.summary.equity_delisted}</div>
                </div>
                <div className="rounded border border-zinc-800 bg-zinc-900/30 p-2">
                  <div className="text-[10px] text-zinc-500">Active + OHLCV</div>
                  <div className="font-mono text-base text-cyan-400">{instrumentStatus.summary.equity_active_with_ohlcv}</div>
                </div>
                <div className="rounded border border-zinc-800 bg-zinc-900/30 p-2">
                  <div className="text-[10px] text-zinc-500">Active, No Data</div>
                  <div className="font-mono text-base text-orange-400">{instrumentStatus.summary.equity_active_without_ohlcv}</div>
                </div>
                <div className="rounded border border-zinc-800 bg-zinc-900/30 p-2">
                  <div className="text-[10px] text-zinc-500">Delisted + Historical</div>
                  <div className="font-mono text-base text-zinc-400">{instrumentStatus.summary.equity_delisted_with_ohlcv}</div>
                </div>
              </div>

              {/* Warning for equity without data */}
              {instrumentStatus.equity_without_data.length > 0 ? (
                <div className="mb-3 rounded border border-orange-800 bg-orange-900/20 p-2 text-xs">
                  <div className="mb-1 font-bold text-orange-400">
                    ⚠ {instrumentStatus.equity_without_data.length} saham listed tanpa OHLCV data:
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {instrumentStatus.equity_without_data.map((t) => (
                      <span key={t.ticker} className="rounded bg-orange-900/30 px-1.5 py-0.5 font-mono text-[10px] text-orange-300">
                        {t.ticker} ({t.name})
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="mb-3 rounded border border-green-800 bg-green-900/20 p-2 text-xs text-green-400">
                  ✓ Semua {instrumentStatus.summary.equity_active} saham listed memiliki OHLCV data
                </div>
              )}

              {/* Delisted equity tickers table */}
              <div className="mb-2 text-[10px] font-bold text-zinc-500">DELISTED SAHAM (engine harus skip)</div>
              <div className="max-h-48 overflow-auto rounded border border-zinc-800">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-zinc-900">
                    <tr className="text-zinc-500">
                      <th className="px-2 py-1 text-left">Ticker</th>
                      <th className="px-2 py-1 text-left">Name</th>
                      <th className="px-2 py-1 text-left">Sector</th>
                      <th className="px-2 py-1 text-left">Listed</th>
                      <th className="px-2 py-1 text-left">Delisted</th>
                      <th className="px-2 py-1 text-left">Board</th>
                    </tr>
                  </thead>
                  <tbody>
                    {instrumentStatus.delisted_equity.map((t) => (
                      <tr key={t.ticker} className="border-t border-zinc-800 text-zinc-400">
                        <td className="px-2 py-0.5 font-mono text-red-400">{t.ticker}</td>
                        <td className="px-2 py-0.5 text-zinc-300">{t.name}</td>
                        <td className="px-2 py-0.5 text-zinc-500">{t.sector}</td>
                        <td className="px-2 py-0.5 font-mono text-zinc-500">{t.listing_date ?? "—"}</td>
                        <td className="px-2 py-0.5 font-mono text-red-400">{t.delisting_date ?? "—"}</td>
                        <td className="px-2 py-0.5 font-mono text-zinc-500">{t.board ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Non-equity reference instruments */}
              <div className="mt-4 mb-2 text-[10px] font-bold text-blue-400">NON-EQUITY REFERENCE INSTRUMENTS (forex, index, commodity, ETF)</div>
              <div className="mb-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <div className="rounded border border-zinc-800 bg-zinc-900/30 p-2">
                  <div className="text-[10px] text-zinc-500">Total Reference</div>
                  <div className="font-mono text-base text-blue-400">{instrumentStatus.summary.non_equity_total}</div>
                </div>
                <div className="rounded border border-zinc-800 bg-zinc-900/30 p-2">
                  <div className="text-[10px] text-zinc-500">With OHLCV</div>
                  <div className="font-mono text-base text-cyan-400">{instrumentStatus.summary.non_equity_with_ohlcv}</div>
                </div>
                <div className="rounded border border-zinc-800 bg-zinc-900/30 p-2">
                  <div className="text-[10px] text-zinc-500">Without OHLCV</div>
                  <div className="font-mono text-base text-orange-400">{instrumentStatus.summary.non_equity_without_ohlcv}</div>
                </div>
                <div className="rounded border border-zinc-800 bg-zinc-900/30 p-2">
                  <div className="text-[10px] text-zinc-500">Asset Classes</div>
                  <div className="font-mono text-base text-zinc-300">
                    {new Set(instrumentStatus.non_equity.map((n) => n.asset_class)).size}
                  </div>
                </div>
              </div>

              {/* Non-equity table */}
              <div className="max-h-40 overflow-auto rounded border border-zinc-800">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-zinc-900">
                    <tr className="text-zinc-500">
                      <th className="px-2 py-1 text-left">Ticker</th>
                      <th className="px-2 py-1 text-left">Name</th>
                      <th className="px-2 py-1 text-left">Class</th>
                      <th className="px-2 py-1 text-left">Exchange</th>
                      <th className="px-2 py-1 text-left">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {instrumentStatus.non_equity.map((t) => {
                      const hasData = !instrumentStatus.non_equity_without_data.some((n) => n.ticker === t.ticker);
                      return (
                        <tr key={t.ticker} className="border-t border-zinc-800 text-zinc-400">
                          <td className="px-2 py-0.5 font-mono text-blue-400">{t.ticker}</td>
                          <td className="px-2 py-0.5 text-zinc-300">{t.name}</td>
                          <td className="px-2 py-0.5 font-mono text-zinc-500">{t.asset_class}</td>
                          <td className="px-2 py-0.5 font-mono text-zinc-500">{t.exchange}</td>
                          <td className="px-2 py-0.5">
                            <span className={`font-mono text-[10px] ${hasData ? "text-green-400" : "text-orange-400"}`}>
                              {hasData ? "HAS DATA" : "NO DATA"}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="mt-2 text-[10px] text-zinc-600">
                Engine/modul/layer selanjutnya hanya memproses <span className="text-green-400">{instrumentStatus.summary.equity_active} saham listed</span> untuk sinyal/rekomendasi.
                Non-equity ({instrumentStatus.summary.non_equity_total} instruments) digunakan sebagai data referensi makro/global, bukan untuk trading signal.
                Delisted saham tetap tersimpan untuk data historis.
              </div>
            </div>
          )}

          {/* ---------- Data Factor Completeness Matrix ---------- */}
          <div id="section-data-factors" className="mb-4 rounded border border-zinc-800 bg-zinc-900/50 p-4">
            <h2 className="mb-3 text-sm font-bold text-zinc-300">Data Factor Completeness</h2>
            <p className="mb-3 text-[10px] text-zinc-500">
              Setiap faktor yang memengaruhi harga saham Indonesia dan status kelengkapan datanya
            </p>
            <div className="space-y-4">
              {Object.entries(factorsByCategory).map(([cat, factors]) => (
                <div key={cat}>
                  <div className="mb-2 flex items-center gap-2">
                    <span className={`rounded border px-2 py-0.5 text-[10px] font-bold ${CATEGORY_COLORS[cat] ?? "text-zinc-400 border-zinc-500/30"}`}>
                      {CATEGORY_LABELS[cat] ?? cat.toUpperCase()}
                    </span>
                    <div className="h-px flex-1 bg-zinc-800" />
                  </div>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {factors.map((f) => {
                      const rows = overview.table_counts[f.key] ?? 0;
                      const status = completenessStatus(rows);
                      return (
                        <div
                          key={f.key}
                          className={`rounded border p-2 ${status.color}`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-zinc-200">{f.label}</span>
                            <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${status.color}`}>
                              {status.label}
                            </span>
                          </div>
                          <div className="mt-1 text-[10px] text-zinc-500">{f.desc}</div>
                          <div className="mt-1.5 flex items-center justify-between">
                            <span className="font-mono text-xs text-zinc-300">{formatNumber(rows)} rows</span>
                            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-zinc-800">
                              <div
                                className={`h-full rounded-full ${
                                  status.pct >= 75 ? "bg-green-500" : status.pct >= 50 ? "bg-yellow-500" : status.pct >= 25 ? "bg-orange-500" : "bg-red-500"
                                }`}
                                style={{ width: `${status.pct}%` }}
                              />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ---------- Two Column: Source Health + Stale Tickers ---------- */}
          <div id="section-source-stale" className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Source Health */}
            <div id="panel-source-health" className="rounded border border-zinc-800 bg-zinc-900/50 p-4">
              <h2 className="mb-3 text-sm font-bold text-zinc-300">Source Health</h2>
              {sourceHealth.length === 0 ? (
                <div className="text-xs text-zinc-600">No source health records</div>
              ) : (
                <div className="space-y-1.5">
                  {sourceHealth.map((s) => (
                    <div key={s.source} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <div className={`h-2 w-2 rounded-full ${s.status === "ok" ? "bg-green-500" : "bg-red-500"}`} />
                        <span className="font-mono text-zinc-300">{s.source}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className={`font-bold ${s.status === "ok" ? "text-green-400" : "text-red-400"}`}>
                          {s.status.toUpperCase()}
                        </span>
                        <span className="font-mono text-[10px] text-zinc-500">
                          {formatDateTime(s.last_success)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {monitor && monitor.alerts.length > 0 && (
                <div className="mt-3 border-t border-zinc-800 pt-2">
                  <div className="mb-1 text-[10px] font-bold text-red-400">ALERTS</div>
                  {monitor.alerts.map((a, i) => (
                    <div key={i} className="text-[10px] text-red-400">
                      {a.source}: {a.last_error ?? a.status}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Stale Tickers */}
            <div id="panel-stale-tickers" className="rounded border border-zinc-800 bg-zinc-900/50 p-4">
              <h2 className="mb-3 text-sm font-bold text-zinc-300">
                Stale Tickers (Top 10)
              </h2>
              {overview.stale_tickers.length === 0 ? (
                <div className="text-xs text-zinc-600">No stale tickers — all data is current</div>
              ) : (
                <div className="overflow-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-zinc-500">
                        <th className="pb-1 text-left">Ticker</th>
                        <th className="pb-1 text-left">Last Date</th>
                        <th className="pb-1 text-right">Rows</th>
                        <th className="pb-1 text-left">Source</th>
                        <th className="pb-1 text-left">Last Fetch</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.stale_tickers.map((t, i) => (
                        <tr key={i} className="border-t border-zinc-800 text-zinc-400">
                          <td className="py-0.5 font-mono text-zinc-200">{t.ticker}</td>
                          <td className="py-0.5 font-mono text-orange-400">{t.last_date}</td>
                          <td className="py-0.5 text-right font-mono">{formatNumber(t.rows)}</td>
                          <td className="py-0.5 font-mono text-zinc-500">{t.source}</td>
                          <td className="py-0.5 font-mono text-[10px] text-zinc-600">{formatDateTime(t.last_fetch)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          {/* ---------- Sector Breakdown ---------- */}
          <div id="section-sector-breakdown" className="mb-4 rounded border border-zinc-800 bg-zinc-900/50 p-4">
            <h2 className="mb-3 text-sm font-bold text-zinc-300">Sector Breakdown</h2>
            {overview.sectors.length === 0 ? (
              <div className="text-xs text-zinc-600">No sector data available</div>
            ) : (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                {overview.sectors.map((s) => (
                  <div key={s.sector} className="rounded border border-zinc-800 bg-zinc-900/30 p-2">
                    <div className="text-xs font-bold text-zinc-200">{s.sector}</div>
                    <div className="font-mono text-lg text-blue-400">{s.count}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ---------- Asset Class Distribution ---------- */}
          <div id="section-asset-class" className="mb-4 rounded border border-zinc-800 bg-zinc-900/50 p-4">
            <h2 className="mb-3 text-sm font-bold text-zinc-300">Asset Class Distribution</h2>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
              {Object.entries(overview.tickers.by_asset_class).map(([cls, count]) => (
                <div key={cls} className="rounded border border-zinc-800 bg-zinc-900/30 p-2">
                  <div className="text-xs font-bold text-zinc-200">{cls}</div>
                  <div className="font-mono text-lg text-amber-400">{count}</div>
                </div>
              ))}
            </div>
          </div>

          {/* ---------- Storage & Sync Info ---------- */}
          {storageInfo && (
            <div id="section-storage-sync" className="mb-4 rounded border border-zinc-800 bg-zinc-900/50 p-4">
              <h2 className="mb-3 text-sm font-bold text-zinc-300">Storage & Parquet Sync</h2>
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                {/* Database */}
                <div id="panel-database-info" className="rounded border border-zinc-800 bg-zinc-900/30 p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="rounded border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 text-[10px] font-bold text-blue-400">DATABASE</span>
                    <span className="rounded border border-green-500/30 bg-green-500/10 px-2 py-0.5 text-[10px] font-bold text-green-400">
                      {storageInfo.database.journal_mode.toUpperCase()}
                    </span>
                  </div>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Path</span>
                      <span className="font-mono text-zinc-300 break-all text-right">{storageInfo.database.path}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Size</span>
                      <span className="font-mono text-zinc-200">{storageInfo.database.size_human}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Pages</span>
                      <span className="font-mono text-zinc-300">{storageInfo.database.page_count.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Page Size</span>
                      <span className="font-mono text-zinc-300">{storageInfo.database.page_size} bytes</span>
                    </div>
                  </div>
                </div>

                {/* Parquet */}
                <div id="panel-parquet-info" className="rounded border border-zinc-800 bg-zinc-900/30 p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-bold text-amber-400">PARQUET</span>
                    <span className={`rounded border px-2 py-0.5 text-[10px] font-bold ${
                      storageInfo.parquet.synced
                        ? "border-green-500/30 bg-green-500/10 text-green-400"
                        : "border-red-500/30 bg-red-500/10 text-red-400"
                    }`}>
                      {storageInfo.parquet.synced ? "SYNCED" : "NOT SYNCED"}
                    </span>
                  </div>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Raw Dir</span>
                      <span className="font-mono text-zinc-300 break-all text-right">{storageInfo.parquet.raw_dir}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Raw Files</span>
                      <span className="font-mono text-zinc-200">{storageInfo.parquet.raw_files} files ({storageInfo.parquet.raw_size_human})</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Archive Dir</span>
                      <span className="font-mono text-zinc-300 break-all text-right">{storageInfo.parquet.archive_dir}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Archive Files</span>
                      <span className="font-mono text-zinc-200">{storageInfo.parquet.archive_files} files ({storageInfo.parquet.archive_size_human})</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ---------- Render Schedule & Recommendations ---------- */}
          {storageInfo && (
            <div id="section-render-schedule" className="mb-4 rounded border border-zinc-800 bg-zinc-900/50 p-4">
              <h2 className="mb-3 text-sm font-bold text-zinc-300">Render Schedule & Recommendations</h2>
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                {/* Render Status */}
                <div id="panel-render-log" className="rounded border border-zinc-800 bg-zinc-900/30 p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="rounded border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 text-[10px] font-bold text-purple-400">RENDER LOG</span>
                    {storageInfo.render.failed > 0 && (
                      <span className="rounded border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-[10px] font-bold text-red-400">
                        {storageInfo.render.failed} FAILED
                      </span>
                    )}
                  </div>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Total Renders</span>
                      <span className="font-mono text-zinc-200">{storageInfo.render.total_renders}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Successful</span>
                      <span className="font-mono text-green-400">{storageInfo.render.ok}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Last Render</span>
                      <span className="font-mono text-zinc-300">{formatDateTime(storageInfo.render.last_render)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Next Trading Day</span>
                      <span className="font-mono text-cyan-400">{storageInfo.render.next_trading_day ?? "—"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Daily Runner</span>
                      <span className="font-mono text-zinc-300">{storageInfo.render.daily_runner_time} {storageInfo.render.daily_runner_once ? "(once)" : "(daily)"}</span>
                    </div>
                  </div>
                  {storageInfo.render.tables.length > 0 && (
                    <div className="mt-3 border-t border-zinc-800 pt-2">
                      <div className="mb-1 text-[10px] text-zinc-500">RENDERED TABLES</div>
                      <div className="space-y-0.5">
                        {storageInfo.render.tables.map((t) => (
                          <div key={t.table} className="flex justify-between text-[10px]">
                            <span className="font-mono text-zinc-400">{t.table}</span>
                            <span className="font-mono text-zinc-500">{t.count} renders · {formatDateTime(t.last_rendered)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Recommendations */}
                <div id="panel-render-recommendations" className="rounded border border-zinc-800 bg-zinc-900/30 p-3">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-bold text-cyan-400">SARAN RENDER</span>
                  </div>
                  <div className="space-y-2">
                    {storageInfo.render.recommendations.map((r, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs">
                        <span className="mt-0.5 text-cyan-400">▸</span>
                        <span className="text-zinc-300">{r}</span>
                      </div>
                    ))}
                  </div>
                  {storageInfo.render.today_is_trading_day !== null && (
                    <div className="mt-3 border-t border-zinc-800 pt-2">
                      <div className={`text-[10px] font-bold ${
                        storageInfo.render.today_is_trading_day ? "text-green-400" : "text-orange-400"
                      }`}>
                        {storageInfo.render.today_is_trading_day
                          ? "Market open today — fetch after 16:00 WIB"
                          : `Market closed${storageInfo.render.today_holiday ? ` (${storageInfo.render.today_holiday})` : ""} — maintenance mode`
                      }
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </TerminalLayout>
  );
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div className="stat-card rounded border border-zinc-800 bg-zinc-900/50 p-3" data-label={label}>
      <div className="text-[10px] text-zinc-500">{label}</div>
      <div className={`mt-1 text-lg font-bold font-mono ${color}`}>{value}</div>
      <div className="mt-0.5 text-[10px] text-zinc-600">{sub}</div>
    </div>
  );
}
