"use client";

import { useEffect, useState } from "react";
import TerminalLayout from "../components/TerminalLayout";

interface Engine {
  name: string;
  status: "healthy" | "idle" | "warning" | "error";
  last_run: string | null;
  latency_ms: number;
  latest_score?: number;
  sample_ticker?: string;
  tickers_in_db?: number;
  score_count?: number;
  error?: string;
}

interface EnginesResponse {
  timestamp: string;
  engines: Engine[];
}

type ConnStatus = "connecting" | "open" | "closed" | "error";

const WS_URL =
  typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8000/ws/live`
    : "ws://localhost:8000/ws/live";

export default function EnginesPage() {
  const [data, setData] = useState<EnginesResponse | null>(null);
  const [status, setStatus] = useState<ConnStatus>("connecting");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnect: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      try {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => setStatus("open");

        ws.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data);
            if (payload?.engines) setData(payload);
          } catch {
            // ignore
          }
        };

        ws.onclose = () => {
          setStatus("closed");
          reconnect = setTimeout(connect, 3000);
        };

        ws.onerror = () => setStatus("error");
      } catch {
        setStatus("error");
        reconnect = setTimeout(connect, 3000);
      }
    };

    connect();

    return () => {
      if (reconnect) clearTimeout(reconnect);
      if (ws) ws.close();
    };
  }, []);

  const healthyCount =
    data?.engines.filter((e) => e.status === "healthy").length ?? 0;
  const errorCount =
    data?.engines.filter((e) => e.status === "error").length ?? 0;

  const selectedEngine =
    data?.engines.find((e) => e.name === selected) ?? null;

  const formatTime = (ts: string | null) => {
    if (!ts) return "—";
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleTimeString("id-ID");
  };

  const statusColor = (s?: string) => {
    switch (s) {
      case "healthy":
        return "border-green-500 bg-green-500/10 text-green-400";
      case "idle":
        return "border-yellow-500 bg-yellow-500/10 text-yellow-400";
      case "warning":
        return "border-orange-500 bg-orange-500/10 text-orange-400";
      default:
        return "border-red-500 bg-red-500/10 text-red-400";
    }
  };

  const statusDot = (s?: string) => {
    switch (s) {
      case "healthy":
        return "bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.6)]";
      case "idle":
        return "bg-yellow-500";
      case "warning":
        return "bg-orange-500";
      default:
        return "bg-red-500";
    }
  };

  const connectionColor = (s: ConnStatus) => {
    if (s === "open") return "text-green-400";
    if (s === "connecting") return "text-yellow-400";
    return "text-red-400";
  };

  return (
    <TerminalLayout active="engines" ticker={data?.engines?.[0]?.sample_ticker || "BBCA.JK"}>
      <div className="mb-3 flex items-baseline justify-between">
        <h1 className="text-xl font-bold tracking-tight text-zinc-100">
          ENGINE MONITOR
        </h1>
        <div className="flex items-center gap-4 font-mono text-xs text-zinc-500">
          <span className={connectionColor(status)}>WS {status.toUpperCase()}</span>
          <span>HEALTHY: {healthyCount}</span>
          <span className="text-red-400">ERRORS: {errorCount}</span>
          <span>LAST: {data ? formatTime(data.timestamp) : "—"}</span>
        </div>
      </div>

      <div className="grid flex-1 grid-cols-4 gap-1 overflow-auto xl:grid-cols-6 2xl:grid-cols-8">
        {data?.engines.map((engine) => (
          <button
            key={engine.name}
            onClick={() => setSelected(engine.name)}
            className={`relative border p-2 text-left transition hover:bg-zinc-800/50 ${selected === engine.name
                ? "border-blue-500 bg-zinc-800/70"
                : "border-zinc-800 bg-zinc-900/50"
              }`}
          >
            <div className="mb-2 flex items-center gap-2">
              <div className={`h-2 w-2 rounded-full ${statusDot(engine.status)}`} />
              <span className="text-xs font-bold uppercase text-zinc-200">
                {engine.name.replace(/_/g, " ")}
              </span>
            </div>
            <div className="font-mono text-[10px] text-zinc-400">
              <div className="flex justify-between">
                <span>LAT</span>
                <span className="text-zinc-200">
                  {engine.latency_ms.toFixed(2)} ms
                </span>
              </div>
              <div className="flex justify-between">
                <span>RUN</span>
                <span className="text-zinc-200">
                  {formatTime(engine.last_run)}
                </span>
              </div>
              {engine.latest_score !== undefined && (
                <div className="flex justify-between">
                  <span>SCORE</span>
                  <span className="text-zinc-200">
                    {engine.latest_score.toFixed(2)}
                  </span>
                </div>
              )}
            </div>
            <div
              className={`absolute left-0 top-0 h-full w-1 ${statusColor(engine.status).split(" ")[0]
                }`}
            />
          </button>
        ))}
      </div>

      <div className="mt-2 flex h-32 gap-2 border-t border-zinc-800 pt-2">
        <div className="flex-1 overflow-auto border border-zinc-800 bg-black/40 p-2 font-mono text-[10px] text-zinc-300">
          <div className="mb-1 text-zinc-500">DETAIL {selected ?? "—"}</div>
          {selectedEngine ? (
            <div className="space-y-1">
              <div className="flex gap-2">
                <span className="w-20 text-zinc-500">STATUS</span>
                <span className={statusColor(selectedEngine.status).split(" ")[2] || "text-zinc-200"}>
                  {selectedEngine.status}
                </span>
              </div>
              <div className="flex gap-2">
                <span className="w-20 text-zinc-500">LATENCY</span>
                <span>{selectedEngine.latency_ms} ms</span>
              </div>
              <div className="flex gap-2">
                <span className="w-20 text-zinc-500">LAST RUN</span>
                <span>{formatTime(selectedEngine.last_run)}</span>
              </div>
              {selectedEngine.sample_ticker && (
                <div className="flex gap-2">
                  <span className="w-20 text-zinc-500">SAMPLE</span>
                  <span>{selectedEngine.sample_ticker}</span>
                </div>
              )}
              {selectedEngine.error && (
                <div className="text-red-400">{selectedEngine.error}</div>
              )}
            </div>
          ) : (
            <div className="text-zinc-600">Click an engine tile for detail</div>
          )}
        </div>
        <div className="w-48 border border-zinc-800 bg-zinc-900/30 p-2 font-mono text-[10px]">
          <div className="text-zinc-500">SYSTEM</div>
          <div className="mt-1 text-zinc-300">
            ENGINES: {data?.engines.length ?? 0}
          </div>
          <div className="text-zinc-300">HEALTHY: {healthyCount}</div>
          <div className="text-red-400">ERRORS: {errorCount}</div>
        </div>
      </div>
    </TerminalLayout>
  );
}
