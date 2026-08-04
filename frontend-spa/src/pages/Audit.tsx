import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../lib/api";

interface AuditLog {
  event_id: number;
  event_type: string;
  timestamp: string;
  payload: string;
}

interface AuditResponse {
  logs: AuditLog[];
  count: number;
}

function eventTypeColor(eventType: string): string {
  if (eventType.startsWith("decision.")) return "text-blue-400";
  if (eventType.startsWith("execution.")) return "text-green-400";
  if (eventType === "error" || eventType.startsWith("error.")) return "text-red-400";
  return "text-zinc-300";
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("id-ID", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function prettyPayload(payload: string): string {
  try {
    return JSON.stringify(JSON.parse(payload), null, 2);
  } catch {
    return payload;
  }
}

export default function Audit() {
  const [eventType, setEventType] = useState("");
  const [ticker, setTicker] = useState("");
  const [limit, setLimit] = useState(50);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [offset, setOffset] = useState(0);

  const [data, setData] = useState<AuditResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("limit", String(limit));
      if (eventType.trim()) params.set("event_type", eventType.trim());
      if (ticker.trim()) params.set("ticker", ticker.trim());
      if (startDate.trim()) params.set("start_date", startDate.trim());
      if (endDate.trim()) params.set("end_date", endDate.trim());
      params.set("offset", String(offset));
      const res = await apiFetch(`/api/audit?${params.toString()}`);
      setData((await res.json()) as AuditResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch audit logs");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [limit, eventType, ticker, startDate, endDate, offset]);

  useEffect(() => {
    fetchLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset, limit]);

  const toggleExpand = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const applyFilters = () => {
    setOffset(0);
    fetchLogs();
  };

  const refresh = () => {
    fetchLogs();
  };

  const nextPage = () => {
    setOffset((o) => o + limit);
  };

  const prevPage = () => {
    setOffset((o) => Math.max(0, o - limit));
  };

  const showingFrom = offset + 1;
  const showingTo = data ? offset + data.logs.length : 0;
  const hasMore = data ? data.logs.length >= limit : false;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-zinc-200">Audit Log</h2>
        <span className="text-[10px] text-zinc-600">
          System event trail · {data ? `${data.count} total` : "—"}
        </span>
      </div>

      {/* Filters */}
      <div className="border border-zinc-800 bg-zinc-900/50 p-3 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1 text-xs text-zinc-400">
            Event type
            <input
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
              placeholder="decision.* / execution.*"
              className="w-40 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>

          <label className="flex items-center gap-1 text-xs text-zinc-400">
            Ticker
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="A.JK"
              className="w-24 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>

          <label className="flex items-center gap-1 text-xs text-zinc-400">
            Limit
            <input
              type="number"
              min={1}
              max={500}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value) || 50)}
              className="w-16 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>

          <label className="flex items-center gap-1 text-xs text-zinc-400">
            Start
            <input
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              placeholder="YYYY-MM-DD"
              className="w-28 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>

          <label className="flex items-center gap-1 text-xs text-zinc-400">
            End
            <input
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              placeholder="YYYY-MM-DD"
              className="w-28 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>

          <button
            onClick={applyFilters}
            disabled={loading}
            className="border border-blue-700 bg-blue-900/30 px-3 py-1 text-xs text-blue-300 hover:bg-blue-900/50 disabled:opacity-50"
          >
            {loading ? "Querying..." : "Apply"}
          </button>

          <button
            onClick={refresh}
            disabled={loading}
            className="border border-zinc-700 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
          >
            Refresh
          </button>
        </div>

        {error && <div className="text-xs text-red-400">{error}</div>}
      </div>

      {/* Table */}
      <div className="border border-zinc-800 bg-zinc-900/50">
        <table className="w-full text-xs">
          <thead className="bg-zinc-900/80 text-[10px] uppercase text-zinc-500">
            <tr>
              <th className="px-2 py-1 text-left w-16">ID</th>
              <th className="px-2 py-1 text-left w-44">Timestamp</th>
              <th className="px-2 py-1 text-left w-40">Event Type</th>
              <th className="px-2 py-1 text-left">Payload</th>
            </tr>
          </thead>
          <tbody>
            {data?.logs.map((log) => {
              const isOpen = expanded.has(log.event_id);
              const pretty = prettyPayload(log.payload);
              const isTruncated = pretty.length > 120;
              return (
                <tr key={log.event_id} className="border-t border-zinc-800/60 align-top hover:bg-zinc-800/30">
                  <td className="px-2 py-1 text-zinc-500 font-mono">{log.event_id}</td>
                  <td className="px-2 py-1 text-zinc-400 font-mono whitespace-nowrap">{formatTimestamp(log.timestamp)}</td>
                  <td className={`px-2 py-1 font-mono ${eventTypeColor(log.event_type)}`}>{log.event_type}</td>
                  <td className="px-2 py-1 text-zinc-300">
                    {isTruncated && !isOpen ? (
                      <button
                        onClick={() => toggleExpand(log.event_id)}
                        className="text-left text-zinc-400 hover:text-zinc-200 font-mono"
                      >
                        {pretty.slice(0, 120)}… <span className="text-blue-400">[expand]</span>
                      </button>
                    ) : (
                      <div className="flex items-start gap-2">
                        {isTruncated && (
                          <button
                            onClick={() => toggleExpand(log.event_id)}
                            className="text-[10px] text-zinc-500 hover:text-zinc-200 mt-0.5"
                          >
                            collapse
                          </button>
                        )}
                        <pre className="font-mono text-[11px] text-zinc-300 whitespace-pre-wrap break-all">{pretty}</pre>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
            {loading && !data && (
              <tr>
                <td colSpan={4} className="px-2 py-4 text-center text-zinc-600">
                  Loading audit logs...
                </td>
              </tr>
            )}
            {data && data.logs.length === 0 && (
              <tr>
                <td colSpan={4} className="px-2 py-4 text-center text-zinc-600">
                  No audit events found for the given filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-xs text-zinc-500">
        <span>
          {data && data.logs.length > 0 ? `Showing ${showingFrom}–${showingTo}` : "No records"}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={prevPage}
            disabled={offset === 0 || loading}
            className="border border-zinc-700 px-2 py-1 text-zinc-300 hover:bg-zinc-800 disabled:opacity-30"
          >
            ← Prev
          </button>
          <span className="font-mono text-zinc-400">offset {offset}</span>
          <button
            onClick={nextPage}
            disabled={!hasMore || loading}
            className="border border-zinc-700 px-2 py-1 text-zinc-300 hover:bg-zinc-800 disabled:opacity-30"
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  );
}
