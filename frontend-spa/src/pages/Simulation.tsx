import { useState } from "react";
import { apiFetch, safeApiFetch } from "../lib/api";

interface PaperTradeResult {
  status: string;
  ticker: string;
  message?: string;
  recommendation?: {
    action: string;
    conviction: number;
    entry_low: number;
    entry_high: number;
    rationale: string;
    position_size?: number;
    stop_loss?: number;
    take_profit?: number;
  };
  order?: {
    action: string;
    ticker: string;
    shares: number;
    target_price: number;
    order_type?: string;
  };
  feasibility?: {
    feasible: boolean;
    required_cash: number;
    available_cash: number;
    slippage_pct: number;
  };
  simulated_fill?: {
    action: string;
    shares: number;
    fill_price: number;
    gross_value: number;
    fees: { brokerage: number; levy: number; tax: number; total: number };
    net_value: number;
    slippage_pct: number;
  };
  timestamp?: string;
}

interface ReplayList {
  tickers: string[];
}

interface ReplayDetail {
  ticker: string;
  [k: string]: unknown;
}

export default function Simulation() {
  const [ticker, setTicker] = useState("BBCA.JK");
  const [capital, setCapital] = useState(100000000);
  const [result, setResult] = useState<PaperTradeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Replay
  const [replayTickers, setReplayTickers] = useState<string[]>([]);
  const [replayDetail, setReplayDetail] = useState<ReplayDetail | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [replayError, setReplayError] = useState("");

  const runPaperTrade = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await apiFetch("/api/paper-trade", {
        method: "POST",
        body: JSON.stringify({ ticker, capital }),
      });
      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Paper trade failed");
    } finally {
      setLoading(false);
    }
  };

  const fetchReplayList = async () => {
    setReplayLoading(true);
    setReplayError("");
    const { data, error } = await safeApiFetch<ReplayList>("/api/replay/list");
    if (error) setReplayError(error.message);
    if (data) setReplayTickers(data.tickers || []);
    setReplayLoading(false);
  };

  const fetchReplayDetail = async (t: string) => {
    setReplayLoading(true);
    setReplayError("");
    setReplayDetail(null);
    const { data, error } = await safeApiFetch<ReplayDetail>(`/api/replay/${t}`);
    if (error) setReplayError(error.message);
    if (data) setReplayDetail(data);
    setReplayLoading(false);
  };

  const fmtRp = (v: number) => `Rp ${v.toLocaleString("id-ID", { maximumFractionDigits: 0 })}`;

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-bold text-zinc-200">Paper Trading Simulation</h2>

      {/* Paper trade config */}
      <div className="border border-zinc-800 bg-zinc-900/50 p-3 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1 text-xs text-zinc-400">
            Ticker
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              className="w-28 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>
          <label className="flex items-center gap-1 text-xs text-zinc-400">
            Capital
            <input
              type="number"
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value) || 100000000)}
              className="w-32 border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-blue-500"
            />
          </label>
          <button
            onClick={runPaperTrade}
            disabled={loading}
            className="border border-blue-700 bg-blue-900/30 px-4 py-1 text-xs text-blue-300 hover:bg-blue-900/50 disabled:opacity-50"
          >
            {loading ? "Simulating..." : "Run Paper Trade"}
          </button>
          <span className="text-[10px] text-zinc-600">
            Generates recommendation → simulates order execution with fees &amp; slippage
          </span>
        </div>
        {error && <div className="text-xs text-red-400">{error}</div>}
      </div>

      {/* Paper trade result */}
      {result && (
        <div className="space-y-3">
          {result.status === "error" ? (
            <div className="border border-red-800 bg-red-950/20 p-3 text-xs text-red-400">
              {result.message || "Simulation failed"}
            </div>
          ) : result.message && !result.order ? (
            <div className="border border-zinc-800 bg-zinc-900/50 p-3 text-xs text-zinc-400">
              {result.message}
            </div>
          ) : (
            <>
              {/* Recommendation */}
              {result.recommendation && (
                <div className="border border-zinc-800 bg-zinc-900/50 p-3">
                  <div className="mb-2 text-[10px] text-zinc-500">RECOMMENDATION</div>
                  <div className="flex items-center gap-4">
                    <span
                      className={`text-xl font-bold ${
                        result.recommendation.action === "BUY"
                          ? "text-green-400"
                          : result.recommendation.action === "SELL"
                            ? "text-red-400"
                            : "text-yellow-400"
                      }`}
                    >
                      {result.recommendation.action}
                    </span>
                    <span className="text-xs text-zinc-400">
                      Conviction: {result.recommendation.conviction.toFixed(1)}
                    </span>
                    {result.recommendation.entry_low > 0 && (
                      <span className="text-xs text-zinc-500">
                        Entry: {result.recommendation.entry_low.toLocaleString()} –{" "}
                        {result.recommendation.entry_high.toLocaleString()}
                      </span>
                    )}
                    {result.recommendation.stop_loss && (
                      <span className="text-xs text-amber-400/70">
                        SL: {result.recommendation.stop_loss.toLocaleString()}
                      </span>
                    )}
                    {result.recommendation.take_profit && (
                      <span className="text-xs text-green-500/70">
                        TP: {result.recommendation.take_profit.toLocaleString()}
                      </span>
                    )}
                  </div>
                  {result.recommendation.rationale && (
                    <div className="mt-2 text-xs text-zinc-400">{result.recommendation.rationale}</div>
                  )}
                </div>
              )}

              {/* Order + feasibility + fill */}
              {result.order && (
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                  <div className="border border-zinc-800 bg-zinc-900/50 p-3">
                    <div className="mb-2 text-[10px] text-zinc-500">SIMULATED ORDER</div>
                    <div className="space-y-1 text-xs">
                      <Row label="Action" value={result.order.action} valueClass="text-zinc-100" />
                      <Row label="Ticker" value={result.order.ticker} valueClass="font-mono text-zinc-100" />
                      <Row label="Shares" value={result.order.shares.toLocaleString()} valueClass="font-mono text-zinc-300" />
                      <Row
                        label="Target Price"
                        value={result.order.target_price.toLocaleString()}
                        valueClass="font-mono text-zinc-300"
                      />
                    </div>
                  </div>

                  {result.feasibility && (
                    <div className="border border-zinc-800 bg-zinc-900/50 p-3">
                      <div className="mb-2 text-[10px] text-zinc-500">FEASIBILITY CHECK</div>
                      <div className="space-y-1 text-xs">
                        <Row
                          label="Feasible"
                          value={result.feasibility.feasible ? "YES" : "NO"}
                          valueClass={result.feasibility.feasible ? "text-green-400" : "text-red-400"}
                        />
                        <Row
                          label="Required Cash"
                          value={fmtRp(result.feasibility.required_cash)}
                          valueClass="font-mono text-zinc-300"
                        />
                        <Row
                          label="Available Cash"
                          value={fmtRp(result.feasibility.available_cash)}
                          valueClass="font-mono text-zinc-300"
                        />
                        <Row
                          label="Slippage"
                          value={`${result.feasibility.slippage_pct}%`}
                          valueClass="font-mono text-amber-400/70"
                        />
                      </div>
                    </div>
                  )}

                  {result.simulated_fill && (
                    <div className="border border-zinc-800 bg-zinc-900/50 p-3">
                      <div className="mb-2 text-[10px] text-zinc-500">SIMULATED FILL</div>
                      <div className="space-y-1 text-xs">
                        <Row
                          label="Fill Price"
                          value={result.simulated_fill.fill_price.toLocaleString()}
                          valueClass="font-mono text-zinc-100"
                        />
                        <Row
                          label="Gross Value"
                          value={fmtRp(result.simulated_fill.gross_value)}
                          valueClass="font-mono text-zinc-300"
                        />
                        <Row
                          label="Fees Total"
                          value={fmtRp(result.simulated_fill.fees.total)}
                          valueClass="font-mono text-amber-400/70"
                        />
                        <Row
                          label="Net Value"
                          value={fmtRp(result.simulated_fill.net_value)}
                          valueClass="font-mono text-zinc-100"
                        />
                        <Row
                          label="Slippage"
                          value={`${result.simulated_fill.slippage_pct}%`}
                          valueClass="font-mono text-amber-400/70"
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}

              {result.timestamp && (
                <div className="text-[10px] text-zinc-600">
                  Simulated at: {new Date(result.timestamp).toLocaleString("id-ID")}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Replay section */}
      <div className="border border-zinc-800 bg-zinc-900/50 p-3 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-zinc-500">REPLAY RESULTS</span>
          <button
            onClick={fetchReplayList}
            disabled={replayLoading}
            className="text-[10px] text-blue-400 hover:text-blue-300 disabled:opacity-50"
          >
            {replayLoading ? "Loading..." : "Load list"}
          </button>
        </div>
        {replayError && <div className="text-xs text-red-400">{replayError}</div>}
        {replayTickers.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {replayTickers.map((t) => (
              <button
                key={t}
                onClick={() => fetchReplayDetail(t)}
                className="border border-zinc-700 bg-zinc-800 px-2 py-1 text-[10px] text-zinc-300 hover:bg-zinc-700"
              >
                {t}
              </button>
            ))}
          </div>
        )}
        {replayTickers.length === 0 && !replayLoading && !replayError && (
          <div className="text-xs text-zinc-600">
            No replay results available. Run daily backtest pipeline to generate replays.
          </div>
        )}
        {replayDetail && (
          <pre className="max-h-64 overflow-auto border border-zinc-800 bg-zinc-950 p-2 text-[10px] text-zinc-400">
            {JSON.stringify(replayDetail, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

function Row({ label, value, valueClass = "text-zinc-300" }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-zinc-500">{label}</span>
      <span className={valueClass}>{value}</span>
    </div>
  );
}
