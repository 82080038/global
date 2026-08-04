import { useCallback, useEffect, useState } from "react";
import { apiFetch, safeApiFetch } from "../lib/api";

interface TickerSummary {
  total: number;
  active: number;
  delisted: number;
  by_asset_class: Record<string, number>;
}

interface SectorRow {
  sector: string;
  count: number;
}

interface DataOverview {
  tickers: TickerSummary;
  sectors: SectorRow[];
  table_counts: Record<string, number>;
}

interface TickerListResponse {
  tickers: string[];
  count: number;
  page: number;
  limit: number;
  pages: number;
}

interface CalendarDay {
  date: string;
  dow: string;
  is_trading_day: boolean;
  holiday_name: string | null;
  half_day: boolean;
  day_type: string;
}

interface MarketCalendar {
  trading_hours: Record<string, string>;
  calendar: CalendarDay[];
}

interface FetchResult {
  status: string;
  message?: string;
  fetched?: Record<string, unknown>;
  errors?: Record<string, string>;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="text-[10px] text-zinc-500">{label}</div>
      <div className="text-lg font-mono text-zinc-100">{value}</div>
    </div>
  );
}

function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="flex items-center justify-between">
      <h3 className="text-xs font-bold text-zinc-200">{children}</h3>
      {hint && <span className="text-[10px] text-zinc-600">{hint}</span>}
    </div>
  );
}

export default function DataPage() {
  const [overview, setOverview] = useState<DataOverview | null>(null);
  const [calendar, setCalendar] = useState<MarketCalendar | null>(null);
  const [tickers, setTickers] = useState<TickerListResponse | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [tickersLoading, setTickersLoading] = useState(false);

  const [fetchTickersInput, setFetchTickersInput] = useState("");
  const [fetchPeriod, setFetchPeriod] = useState("2y");
  const [fetching, setFetching] = useState(false);
  const [fetchResult, setFetchResult] = useState<FetchResult | null>(null);
  const [fetchError, setFetchError] = useState("");

  const [overviewError, setOverviewError] = useState("");
  const [calendarError, setCalendarError] = useState("");
  const [tickersError, setTickersError] = useState("");

  const loadOverview = useCallback(async () => {
    setOverviewError("");
    const { data, error } = await safeApiFetch<DataOverview>("/api/data-overview");
    if (error) setOverviewError(error.message);
    if (data) setOverview(data);
  }, []);

  const loadCalendar = useCallback(async () => {
    setCalendarError("");
    const { data, error } = await safeApiFetch<MarketCalendar>("/api/market-calendar");
    if (error) setCalendarError(error.message);
    if (data) setCalendar(data);
  }, []);

  const loadTickers = useCallback(async () => {
    setTickersLoading(true);
    setTickersError("");
    try {
      const res = await apiFetch(`/api/tickers?limit=50&page=${page}`);
      setTickers((await res.json()) as TickerListResponse);
    } catch (e) {
      setTickersError(e instanceof Error ? e.message : "Failed to load tickers");
      setTickers(null);
    } finally {
      setTickersLoading(false);
    }
  }, [page]);

  useEffect(() => {
    loadOverview();
    loadCalendar();
  }, [loadOverview, loadCalendar]);

  useEffect(() => {
    loadTickers();
  }, [loadTickers]);

  const runFetch = useCallback(async () => {
    const list = fetchTickersInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    if (list.length === 0) {
      setFetchError("Enter at least one ticker.");
      return;
    }
    setFetching(true);
    setFetchError("");
    setFetchResult(null);
    try {
      const res = await apiFetch("/api/fetch", {
        method: "POST",
        body: JSON.stringify({ tickers: list, period: fetchPeriod }),
      });
      setFetchResult((await res.json()) as FetchResult);
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : "Fetch failed");
    } finally {
      setFetching(false);
    }
  }, [fetchTickersInput, fetchPeriod]);

  const filteredTickers = tickers
    ? search.trim()
      ? tickers.tickers.filter((t) => t.toLowerCase().includes(search.trim().toLowerCase()))
      : tickers.tickers
    : [];

  const tableCountKeys = ["ohlcv", "technical_indicators", "fundamental_data", "scores", "foreign_flow"];
  const maxCount = overview
    ? Math.max(...tableCountKeys.map((k) => overview.table_counts[k] ?? 0), 1)
    : 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-zinc-200">Data Application</h2>
        <span className="text-[10px] text-zinc-600">IDX universe · SQLite storage</span>
      </div>

      {/* Data Overview */}
      <section className="space-y-2">
        <SectionTitle hint="GET /api/data-overview">Data Overview</SectionTitle>
        {overviewError && <div className="text-xs text-red-400">{overviewError}</div>}
        {overview ? (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="TOTAL TICKERS" value={String(overview.tickers.total)} />
              <Stat label="ACTIVE" value={String(overview.tickers.active)} />
              <Stat label="DELISTED" value={String(overview.tickers.delisted)} />
              <Stat
                label="ASSET CLASSES"
                value={String(Object.keys(overview.tickers.by_asset_class).length)}
              />
            </div>

            {Object.keys(overview.tickers.by_asset_class).length > 0 && (
              <div className="border border-zinc-800 bg-zinc-900/50 p-3">
                <div className="text-[10px] uppercase text-zinc-500 mb-2">By Asset Class</div>
                <div className="flex flex-wrap gap-3">
                  {Object.entries(overview.tickers.by_asset_class).map(([cls, n]) => (
                    <div key={cls} className="flex items-center gap-2 text-xs">
                      <span className="text-zinc-400">{cls}</span>
                      <span className="font-mono text-zinc-100">{n}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="border border-zinc-800 bg-zinc-900/50">
              <div className="text-[10px] uppercase text-zinc-500 px-3 py-2 border-b border-zinc-800">
                Sector Distribution
              </div>
              <table className="w-full text-xs">
                <thead className="bg-zinc-900/80 text-[10px] uppercase text-zinc-500">
                  <tr>
                    <th className="px-2 py-1 text-left">Sector</th>
                    <th className="px-2 py-1 text-right w-24">Count</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.sectors.map((s) => (
                    <tr key={s.sector} className="border-t border-zinc-800/60 hover:bg-zinc-800/30">
                      <td className="px-2 py-1 text-zinc-300">{s.sector}</td>
                      <td className="px-2 py-1 text-right font-mono text-zinc-100">{s.count}</td>
                    </tr>
                  ))}
                  {overview.sectors.length === 0 && (
                    <tr>
                      <td colSpan={2} className="px-2 py-3 text-center text-zinc-600">
                        No sector data.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          !overviewError && <div className="text-xs text-zinc-600">Loading overview...</div>
        )}
      </section>

      {/* Table Counts */}
      <section className="space-y-2">
        <SectionTitle hint="Row counts per table">Table Counts</SectionTitle>
        <div className="border border-zinc-800 bg-zinc-900/50 p-3 space-y-2">
          {overview ? (
            tableCountKeys.map((k) => {
              const n = overview.table_counts[k] ?? 0;
              const pct = (n / maxCount) * 100;
              return (
                <div key={k} className="flex items-center gap-3 text-xs">
                  <span className="w-44 text-zinc-400">{k}</span>
                  <div className="flex-1 h-2 bg-zinc-800">
                    <div className="h-full bg-blue-500/60" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="w-20 text-right font-mono text-zinc-100">{n.toLocaleString()}</span>
                </div>
              );
            })
          ) : (
            <div className="text-xs text-zinc-600">{overviewError ? "No data" : "Loading..."}</div>
          )}
        </div>
      </section>

      {/* Ticker Browser */}
      <section className="space-y-2">
        <SectionTitle hint="GET /api/tickers?limit=50">Ticker Browser</SectionTitle>
        <div className="border border-zinc-800 bg-zinc-900/50 p-3 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter by symbol..."
              className="w-48 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
            <span className="text-[10px] text-zinc-600">
              {tickers ? `${tickers.count} total · page ${tickers.page}/${tickers.pages || 1}` : "—"}
            </span>
            <div className="ml-auto flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || tickersLoading}
                className="border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-30"
              >
                ← Prev
              </button>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={!tickers || page >= (tickers.pages || 1) || tickersLoading}
                className="border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-30"
              >
                Next →
              </button>
            </div>
          </div>
          {tickersError && <div className="text-xs text-red-400">{tickersError}</div>}
          <div className="grid grid-cols-2 gap-1 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8">
            {filteredTickers.map((t) => (
              <div key={t} className="border border-zinc-800 px-2 py-1 font-mono text-xs text-zinc-300 hover:bg-zinc-800/40">
                {t}
              </div>
            ))}
            {tickersLoading && (
              <div className="col-span-full text-xs text-zinc-600">Loading tickers...</div>
            )}
            {!tickersLoading && filteredTickers.length === 0 && (
              <div className="col-span-full text-xs text-zinc-600">No tickers.</div>
            )}
          </div>
        </div>
      </section>

      {/* Fetch Data */}
      <section className="space-y-2">
        <SectionTitle hint="POST /api/fetch · Yahoo Finance">Fetch Data</SectionTitle>
        <div className="border border-zinc-800 bg-zinc-900/50 p-3 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1 text-xs text-zinc-400">
              Tickers
              <input
                value={fetchTickersInput}
                onChange={(e) => setFetchTickersInput(e.target.value)}
                placeholder="A.JK,B.JK,TLKM.JK"
                className="w-56 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
              />
            </label>
            <label className="flex items-center gap-1 text-xs text-zinc-400">
              Period
              <select
                value={fetchPeriod}
                onChange={(e) => setFetchPeriod(e.target.value)}
                className="border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
              >
                {["1y", "2y", "5y", "max"].map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={runFetch}
              disabled={fetching}
              className="border border-blue-700 bg-blue-900/30 px-3 py-1 text-xs text-blue-300 hover:bg-blue-900/50 disabled:opacity-50"
            >
              {fetching ? "Fetching..." : "Fetch"}
            </button>
          </div>
          {fetchError && <div className="text-xs text-red-400">{fetchError}</div>}
          {fetchResult && (
            <div className="border border-zinc-800 bg-zinc-950 p-3 space-y-2">
              <div className="flex items-center gap-2 text-xs">
                <span className="text-zinc-500">Status:</span>
                <span
                  className={
                    fetchResult.status === "ok" || fetchResult.status === "success"
                      ? "text-green-400 font-mono"
                      : "text-amber-400 font-mono"
                  }
                >
                  {fetchResult.status}
                </span>
              </div>
              {fetchResult.message && <div className="text-xs text-zinc-300">{fetchResult.message}</div>}
              {fetchResult.fetched && Object.keys(fetchResult.fetched).length > 0 && (
                <div className="text-xs">
                  <div className="text-[10px] uppercase text-zinc-500 mb-1">Fetched</div>
                  <pre className="font-mono text-[11px] text-green-400 whitespace-pre-wrap">
                    {JSON.stringify(fetchResult.fetched, null, 2)}
                  </pre>
                </div>
              )}
              {fetchResult.errors && Object.keys(fetchResult.errors).length > 0 && (
                <div className="text-xs">
                  <div className="text-[10px] uppercase text-zinc-500 mb-1">Errors</div>
                  <pre className="font-mono text-[11px] text-red-400 whitespace-pre-wrap">
                    {JSON.stringify(fetchResult.errors, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Market Calendar (compact reference) */}
      <section className="space-y-2">
        <SectionTitle hint="GET /api/market-calendar">Market Calendar (next 7 days)</SectionTitle>
        {calendarError && <div className="text-xs text-red-400">{calendarError}</div>}
        <div className="border border-zinc-800 bg-zinc-900/50">
          <table className="w-full text-xs">
            <thead className="bg-zinc-900/80 text-[10px] uppercase text-zinc-500">
              <tr>
                <th className="px-2 py-1 text-left">Date</th>
                <th className="px-2 py-1 text-left w-16">DOW</th>
                <th className="px-2 py-1 text-left">Type</th>
                <th className="px-2 py-1 text-left">Note</th>
              </tr>
            </thead>
            <tbody>
              {calendar?.calendar.slice(0, 7).map((d) => (
                <tr key={d.date} className="border-t border-zinc-800/60 hover:bg-zinc-800/30">
                  <td className="px-2 py-1 font-mono text-zinc-300">{d.date}</td>
                  <td className="px-2 py-1 text-zinc-500">{d.dow}</td>
                  <td className="px-2 py-1">
                    <span
                      className={
                        d.is_trading_day
                          ? d.half_day
                            ? "text-amber-400"
                            : "text-green-400"
                          : "text-red-400"
                      }
                    >
                      {d.is_trading_day ? (d.half_day ? "HALF" : "TRADING") : "HOLIDAY"}
                    </span>
                  </td>
                  <td className="px-2 py-1 text-zinc-500">{d.holiday_name ?? "—"}</td>
                </tr>
              ))}
              {!calendar && !calendarError && (
                <tr>
                  <td colSpan={4} className="px-2 py-3 text-center text-zinc-600">
                    Loading calendar...
                  </td>
                </tr>
              )}
              {calendar && calendar.calendar.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-2 py-3 text-center text-zinc-600">
                    No calendar data.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
