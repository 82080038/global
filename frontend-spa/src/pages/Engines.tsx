import { useEffect, useState } from "react";
import { safeApiFetch } from "../lib/api";

interface EngineHealth {
  name: string;
  status: string;
  timestamp: string;
  tickers_in_db?: number;
  score_count?: number;
}

export default function Engines() {
  const [engines, setEngines] = useState<EngineHealth[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const { data } = await safeApiFetch<EngineHealth[]>("/api/health");
      if (data) setEngines(Array.isArray(data) ? data : [data]);
      setLoading(false);
    })();
  }, []);

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-bold text-zinc-200">Engine Monitor</h2>
      {loading ? (
        <div className="text-xs text-zinc-500">Loading...</div>
      ) : (
        <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
          {engines.map((e) => (
            <div key={e.name} className="border border-zinc-800 bg-zinc-900/50 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-zinc-200">{e.name}</span>
                <span
                  className={`text-[10px] ${
                    e.status === "ok" ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {e.status}
                </span>
              </div>
              <div className="mt-1 text-[10px] text-zinc-500">
                {e.timestamp ? `Last: ${new Date(e.timestamp).toLocaleString("id-ID")}` : "—"}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
