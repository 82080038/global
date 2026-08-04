import { useCallback, useEffect, useState } from "react";
import { safeApiFetch } from "../lib/api";

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

interface ExecutionToggle {
  auto_trade_enabled: boolean;
  [k: string]: unknown;
}

interface RebalanceToggle {
  enabled: boolean;
  [k: string]: unknown;
}

interface EngineEntry {
  name: string;
  engine?: string;
  status?: string;
  last_run?: string;
  last_run_at?: string;
  next_run?: string;
  interval?: string;
  enabled?: boolean;
  running?: boolean;
  [k: string]: unknown;
}

interface SystemStateValue {
  key: string;
  value: unknown;
  error?: string;
}

function formatTimestamp(ts?: string): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("id-ID", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="flex items-center justify-between">
      <h3 className="text-xs font-bold text-zinc-200">{children}</h3>
      {hint && <span className="text-[10px] text-zinc-600">{hint}</span>}
    </div>
  );
}

const SYSTEM_STATE_KEYS = ["market_status", "last_rebalance", "last_decision", "session_state"];

export default function Schedule() {
  const [calendar, setCalendar] = useState<MarketCalendar | null>(null);
  const [calendarError, setCalendarError] = useState("");

  const [execToggle, setExecToggle] = useState<ExecutionToggle | null>(null);
  const [execError, setExecError] = useState("");

  const [rebalToggle, setRebalToggle] = useState<RebalanceToggle | null>(null);
  const [rebalError, setRebalError] = useState("");

  const [engines, setEngines] = useState<EngineEntry[] | null>(null);
  const [enginesError, setEnginesError] = useState("");

  const [systemStates, setSystemStates] = useState<SystemStateValue[]>([]);
  const [loading, setLoading] = useState(true);

  const loadAll = useCallback(async () => {
    setLoading(true);
    const [calRes, execRes, rebalRes, engRes] = await Promise.all([
      safeApiFetch<MarketCalendar>("/api/market-calendar"),
      safeApiFetch<ExecutionToggle>("/api/execution/toggle"),
      safeApiFetch<RebalanceToggle>("/api/rebalance/toggle"),
      safeApiFetch<EngineEntry[] | { engines: EngineEntry[] }>("/api/engines"),
    ]);

    if (calRes.error) setCalendarError(calRes.error.message);
    else setCalendar(calRes.data);
    setCalendarError(calRes.error ? calRes.error.message : "");

    if (execRes.error) setExecError(execRes.error.message);
    else setExecToggle(execRes.data);
    setExecError(execRes.error ? execRes.error.message : "");

    if (rebalRes.error) setRebalError(rebalRes.error.message);
    else setRebalToggle(rebalRes.data);
    setRebalError(rebalRes.error ? rebalRes.error.message : "");

    if (engRes.error) {
      setEnginesError(engRes.error.message);
      setEngines(null);
    } else if (engRes.data) {
      const list = Array.isArray(engRes.data) ? engRes.data : engRes.data.engines ?? [];
      setEngines(list);
      setEnginesError("");
    }

    // System state keys (best-effort, read-only)
    const stateResults = await Promise.all(
      SYSTEM_STATE_KEYS.map(async (key) => {
        const { data, error } = await safeApiFetch<unknown>(`/api/system-state/${key}`);
        return { key, value: data, error: error ? error.message : undefined };
      }),
    );
    setSystemStates(stateResults);

    setLoading(false);
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const calendarRows = calendar?.calendar.slice(0, 14) ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-zinc-200">Schedule &amp; Calendar</h2>
        <button
          onClick={loadAll}
          disabled={loading}
          className="border border-zinc-700 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {/* Trading Hours */}
      <section className="space-y-2">
        <SectionTitle hint="GET /api/market-calendar · trading_hours">Trading Hours</SectionTitle>
        <div className="border border-zinc-800 bg-zinc-900/50 p-3">
          {calendarError ? (
            <div className="text-xs text-red-400">{calendarError}</div>
          ) : calendar && calendar.trading_hours ? (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(calendar.trading_hours).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between border border-zinc-800 px-2 py-1">
                  <span className="text-[10px] uppercase text-zinc-500">{k}</span>
                  <span className="font-mono text-xs text-zinc-200">{v || "—"}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-zinc-600">{loading ? "Loading..." : "No trading hours data."}</div>
          )}
        </div>
      </section>

      {/* Market Calendar */}
      <section className="space-y-2">
        <SectionTitle hint="Next 14 days · green=trading, red=holiday">Market Calendar</SectionTitle>
        <div className="border border-zinc-800 bg-zinc-900/50">
          <table className="w-full text-xs">
            <thead className="bg-zinc-900/80 text-[10px] uppercase text-zinc-500">
              <tr>
                <th className="px-2 py-1 text-left">Date</th>
                <th className="px-2 py-1 text-left w-16">DOW</th>
                <th className="px-2 py-1 text-left w-24">Type</th>
                <th className="px-2 py-1 text-left">Note</th>
              </tr>
            </thead>
            <tbody>
              {calendarRows.map((d) => {
                const trading = d.is_trading_day;
                return (
                  <tr
                    key={d.date}
                    className={`border-t border-zinc-800/60 hover:bg-zinc-800/30 ${
                      trading ? "bg-green-950/10" : "bg-red-950/10"
                    }`}
                  >
                    <td className="px-2 py-1 font-mono text-zinc-200">{d.date}</td>
                    <td className="px-2 py-1 text-zinc-500">{d.dow}</td>
                    <td className="px-2 py-1">
                      <span
                        className={
                          trading ? (d.half_day ? "text-amber-400" : "text-green-400") : "text-red-400"
                        }
                      >
                        {trading ? (d.half_day ? "HALF DAY" : "TRADING") : "HOLIDAY"}
                      </span>
                    </td>
                    <td className="px-2 py-1 text-zinc-400">{d.holiday_name ?? (d.day_type && d.day_type !== "trading" ? d.day_type : "—")}</td>
                  </tr>
                );
              })}
              {!calendar && !calendarError && (
                <tr>
                  <td colSpan={4} className="px-2 py-3 text-center text-zinc-600">
                    Loading calendar...
                  </td>
                </tr>
              )}
              {calendar && calendarRows.length === 0 && (
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

      {/* Runtime Toggles (read-only) */}
      <section className="space-y-2">
        <SectionTitle hint="Read-only display · sensitive controls">Runtime Toggles</SectionTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="border border-zinc-800 bg-zinc-900/50 p-3 space-y-1">
            <div className="text-[10px] uppercase text-zinc-500">Auto Trade</div>
            {execError ? (
              <div className="text-xs text-red-400">{execError}</div>
            ) : execToggle ? (
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block h-2 w-2 rounded-full ${
                    execToggle.auto_trade_enabled ? "bg-green-400" : "bg-zinc-600"
                  }`}
                />
                <span
                  className={`font-mono text-sm ${
                    execToggle.auto_trade_enabled ? "text-green-400" : "text-zinc-400"
                  }`}
                >
                  {execToggle.auto_trade_enabled ? "ENABLED" : "DISABLED"}
                </span>
              </div>
            ) : (
              <div className="text-xs text-zinc-600">{loading ? "Loading..." : "No data"}</div>
            )}
          </div>

          <div className="border border-zinc-800 bg-zinc-900/50 p-3 space-y-1">
            <div className="text-[10px] uppercase text-zinc-500">Rebalance</div>
            {rebalError ? (
              <div className="text-xs text-red-400">{rebalError}</div>
            ) : rebalToggle ? (
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block h-2 w-2 rounded-full ${
                    rebalToggle.enabled ? "bg-green-400" : "bg-zinc-600"
                  }`}
                />
                <span
                  className={`font-mono text-sm ${
                    rebalToggle.enabled ? "text-green-400" : "text-zinc-400"
                  }`}
                >
                  {rebalToggle.enabled ? "ENABLED" : "DISABLED"}
                </span>
              </div>
            ) : (
              <div className="text-xs text-zinc-600">{loading ? "Loading..." : "No data"}</div>
            )}
          </div>
        </div>
        <div className="text-[10px] text-zinc-600">
          These are read-only status indicators. Toggling is a sensitive operation not exposed in the UI.
        </div>
      </section>

      {/* System State */}
      <section className="space-y-2">
        <SectionTitle hint="GET /api/system-state/{key}">System State</SectionTitle>
        <div className="border border-zinc-800 bg-zinc-900/50">
          <table className="w-full text-xs">
            <thead className="bg-zinc-900/80 text-[10px] uppercase text-zinc-500">
              <tr>
                <th className="px-2 py-1 text-left w-48">Key</th>
                <th className="px-2 py-1 text-left">Value</th>
              </tr>
            </thead>
            <tbody>
              {systemStates.map((s) => (
                <tr key={s.key} className="border-t border-zinc-800/60 hover:bg-zinc-800/30">
                  <td className="px-2 py-1 font-mono text-zinc-400">{s.key}</td>
                  <td className="px-2 py-1 font-mono text-zinc-200">
                    {s.error ? (
                      <span className="text-zinc-600">—</span>
                    ) : s.value === null || s.value === undefined ? (
                      <span className="text-zinc-600">—</span>
                    ) : typeof s.value === "object" ? (
                      <pre className="text-[11px] text-zinc-300 whitespace-pre-wrap">
                        {JSON.stringify(s.value)}
                      </pre>
                    ) : (
                      String(s.value)
                    )}
                  </td>
                </tr>
              ))}
              {!loading && systemStates.length === 0 && (
                <tr>
                  <td colSpan={2} className="px-2 py-3 text-center text-zinc-600">
                    No system state data.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Engine Schedule */}
      <section className="space-y-2">
        <SectionTitle hint="GET /api/engines">Engine Schedule</SectionTitle>
        {enginesError && <div className="text-xs text-red-400">{enginesError}</div>}
        <div className="border border-zinc-800 bg-zinc-900/50">
          <table className="w-full text-xs">
            <thead className="bg-zinc-900/80 text-[10px] uppercase text-zinc-500">
              <tr>
                <th className="px-2 py-1 text-left">Engine</th>
                <th className="px-2 py-1 text-left w-24">Status</th>
                <th className="px-2 py-1 text-left w-28">Enabled</th>
                <th className="px-2 py-1 text-left w-44">Last Run</th>
                <th className="px-2 py-1 text-left w-44">Next Run</th>
                <th className="px-2 py-1 text-left w-24">Interval</th>
              </tr>
            </thead>
            <tbody>
              {engines?.map((eng, i) => {
                const name = String(eng.name ?? eng.engine ?? `engine-${i}`);
                const status = String(eng.status ?? (eng.running ? "running" : "idle"));
                const lastRun = eng.last_run ?? eng.last_run_at;
                return (
                  <tr key={name} className="border-t border-zinc-800/60 hover:bg-zinc-800/30">
                    <td className="px-2 py-1 font-mono text-zinc-200">{name}</td>
                    <td className="px-2 py-1">
                      <span
                        className={
                          status === "running" || status === "ok" || status === "active"
                            ? "text-green-400"
                            : status === "error" || status === "failed"
                              ? "text-red-400"
                              : "text-zinc-400"
                        }
                      >
                        {status}
                      </span>
                    </td>
                    <td className="px-2 py-1">
                      <span
                        className={
                          eng.enabled === false ? "text-zinc-500" : "text-green-400"
                        }
                      >
                        {eng.enabled === false ? "OFF" : "ON"}
                      </span>
                    </td>
                    <td className="px-2 py-1 font-mono text-zinc-400">{formatTimestamp(lastRun)}</td>
                    <td className="px-2 py-1 font-mono text-zinc-400">{formatTimestamp(eng.next_run)}</td>
                    <td className="px-2 py-1 font-mono text-zinc-500">{eng.interval ?? "—"}</td>
                  </tr>
                );
              })}
              {!engines && !enginesError && (
                <tr>
                  <td colSpan={6} className="px-2 py-3 text-center text-zinc-600">
                    Loading engines...
                  </td>
                </tr>
              )}
              {engines && engines.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-2 py-3 text-center text-zinc-600">
                    No engines registered.
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
