"use client";

import { useEffect, useState } from "react";

export default function TerminalLayout({
  active,
  children,
  ticker = "BBCA.JK",
}: {
  active: "dashboard" | "engines" | "backtest" | "portfolio" | "audit" | "replay" | "simulation";
  children: React.ReactNode;
  ticker?: string;
}) {
  const [time, setTime] = useState("");

  useEffect(() => {
    const update = () => setTime(new Date().toLocaleTimeString("id-ID"));
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <main className="flex min-h-screen flex-col bg-zinc-950 text-zinc-100">
      <header className="flex items-center border-b border-zinc-800 bg-zinc-900/80 px-4 py-2 text-xs font-mono">
        <div className="mr-4 font-bold text-blue-400">TS-MON</div>
        <div className="flex gap-6 text-zinc-300">
          <span className="text-green-400">LIVE</span>
          <span>{ticker}</span>
          <span>{time}</span>
        </div>
        <div className="ml-auto flex gap-4">
          <a
            href="/dashboard"
            className={
              active === "dashboard"
                ? "text-zinc-100"
                : "text-zinc-400 hover:text-zinc-100"
            }
          >
            DASHBOARD
          </a>
          <a
            href="/engines"
            className={
              active === "engines"
                ? "text-zinc-100"
                : "text-zinc-400 hover:text-zinc-100"
            }
          >
            ENGINES
          </a>
          <a
            href="/simulation"
            className={
              active === "simulation"
                ? "text-zinc-100"
                : "text-zinc-400 hover:text-zinc-100"
            }
          >
            SIMULATION
          </a>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-48 border-r border-zinc-800 bg-zinc-900/50 p-2 text-xs">
          <div className="mb-2 px-2 py-1 text-zinc-500">NAVIGATION</div>
          <a
            href="/dashboard"
            className={`block rounded px-2 py-1 ${active === "dashboard"
              ? "bg-zinc-800 text-zinc-100"
              : "text-zinc-300 hover:bg-zinc-800"
              }`}
          >
            Dashboard
          </a>
          <a
            href="/engines"
            className={`block rounded px-2 py-1 ${active === "engines"
              ? "bg-zinc-800 text-zinc-100"
              : "text-zinc-300 hover:bg-zinc-800"
              }`}
          >
            Engine Monitor
          </a>
          <a
            href="/backtest"
            className={`block rounded px-2 py-1 ${active === "backtest"
              ? "bg-zinc-800 text-zinc-100"
              : "text-zinc-300 hover:bg-zinc-800"
              }`}
          >
            Backtest
          </a>
          <a
            href="/portfolio"
            className={`block rounded px-2 py-1 ${active === "portfolio"
              ? "bg-zinc-800 text-zinc-100"
              : "text-zinc-300 hover:bg-zinc-800"
              }`}
          >
            Portfolio
          </a>
          <a
            href="/audit"
            className={`block rounded px-2 py-1 ${active === "audit"
              ? "bg-zinc-800 text-zinc-100"
              : "text-zinc-300 hover:bg-zinc-800"
              }`}
          >
            Audit Log
          </a>
          <a
            href="/replay"
            className={`block rounded px-2 py-1 ${active === "replay"
              ? "bg-zinc-800 text-zinc-100"
              : "text-zinc-300 hover:bg-zinc-800"
              }`}
          >
            Replay Sim
          </a>
          <a
            href="/simulation"
            className={`block rounded px-2 py-1 ${active === "simulation"
              ? "bg-zinc-800 text-zinc-100"
              : "text-zinc-300 hover:bg-zinc-800"
              }`}
          >
            Simulation
          </a>
          <div className="mt-6 px-2 py-1 text-zinc-500">SYSTEM</div>
          <div className="px-2 py-1 text-zinc-400">v0.1.7</div>
        </aside>

        <section className="flex flex-1 flex-col overflow-auto p-4">
          {children}
        </section>
      </div>
    </main>
  );
}
