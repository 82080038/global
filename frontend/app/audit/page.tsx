"use client";

import { useEffect, useState } from "react";
import TerminalLayout from "../components/TerminalLayout";
import { apiFetch } from "../lib/api";

interface AuditEntry {
  event_id: number;
  event_type: string;
  payload: string;
  timestamp: string;
  actor: string;
}

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const fetchAudit = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch("/api/audit?limit=100");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setEntries(data.logs || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load audit log");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const init = async () => {
      await fetchAudit();
    };
    init();
  }, []);

  const filtered = filter
    ? entries.filter(
        (e) =>
          e.event_type?.toLowerCase().includes(filter.toLowerCase()) ||
          e.payload?.toLowerCase().includes(filter.toLowerCase())
      )
    : entries;

  return (
    <TerminalLayout active="audit">
      <div className="mb-4">
        <h1 className="mb-2 text-lg font-bold text-zinc-100">Audit Log</h1>
        <p className="text-xs text-zinc-500">
          System audit trail — all data quality, execution, and engine events
        </p>
      </div>

      <div className="mb-4 flex gap-2">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by action or detail..."
          className="flex-1 rounded border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-100"
        />
        <button
          onClick={fetchAudit}
          className="rounded bg-zinc-800 px-4 py-1 text-xs font-bold text-zinc-300 hover:bg-zinc-700"
        >
          Refresh
        </button>
      </div>

      {loading && <div className="text-xs text-zinc-500">Loading...</div>}

      {error && (
        <div className="mb-4 rounded border border-red-800 bg-red-900/30 p-3 text-xs text-red-400">
          {error}
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <div className="overflow-auto rounded border border-zinc-800 bg-zinc-900/50">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-zinc-900">
              <tr className="text-zinc-500">
                <th className="px-3 py-1 text-left">ID</th>
                <th className="px-3 py-1 text-left">Timestamp</th>
                <th className="px-3 py-1 text-left">Event Type</th>
                <th className="px-3 py-1 text-left">Actor</th>
                <th className="px-3 py-1 text-left">Payload</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry, i) => (
                <tr
                  key={i}
                  className="border-t border-zinc-800 text-zinc-400 hover:bg-zinc-800/30"
                >
                  <td className="px-3 py-1 text-zinc-600">{entry.event_id}</td>
                  <td className="px-3 py-1 font-mono">{entry.timestamp}</td>
                  <td className="px-3 py-1 font-mono text-blue-400">{entry.event_type}</td>
                  <td className="px-3 py-1 font-mono text-zinc-300">{entry.actor}</td>
                  <td className="px-3 py-1 max-w-xs truncate" title={entry.payload}>{entry.payload}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && filtered.length === 0 && !error && (
        <div className="text-xs text-zinc-600">No audit entries found.</div>
      )}
    </TerminalLayout>
  );
}
