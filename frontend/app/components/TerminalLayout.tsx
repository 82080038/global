"use client";

import { useEffect, useState } from "react";

export default function TerminalLayout({
  active,
  children,
  ticker = "BBCA.JK",
}: {
  active: "home";
  children: React.ReactNode;
  ticker?: string;
}) {
  const [time, setTime] = useState("");
  const [fullPage, setFullPage] = useState(false);

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
        <div className="ml-auto flex items-center gap-4">
          <a
            href="/"
            className={
              active === "home"
                ? "text-zinc-100"
                : "text-zinc-400 hover:text-zinc-100"
            }
          >
            DATA INSPECTION
          </a>
          <div className="h-4 w-px bg-zinc-700" />
          <button
            onClick={() => setFullPage((v) => !v)}
            title={fullPage ? "Show sidebar" : "Hide sidebar (full page)"}
            className="flex items-center gap-1 text-zinc-500 hover:text-zinc-200 transition-colors"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className={fullPage ? "rotate-180" : ""} style={{ transition: "transform 0.2s" }}>
              <rect x="1" y="2" width="14" height="12" rx="1" stroke="currentColor" strokeWidth="1.2" />
              <rect x="1" y="2" width="4" height="12" fill="currentColor" opacity={fullPage ? 0.2 : 0.5} rx="1" />
            </svg>
            <span className="text-[10px]">{fullPage ? "EXPAND" : "COLLAPSE"}</span>
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className={`border-r border-zinc-800 bg-zinc-900/50 p-2 text-xs transition-all duration-200 overflow-hidden ${
          fullPage ? "w-0 border-r-0 p-0" : "w-48"
        }`} style={fullPage ? { opacity: 0 } : { opacity: 1 }}>
          <div className="mb-2 px-2 py-1 text-zinc-500">NAVIGATION</div>
          <a
            href="/"
            className={`block rounded px-2 py-1 ${active === "home"
              ? "bg-zinc-800 text-zinc-100"
              : "text-zinc-300 hover:bg-zinc-800"
              }`
            }
          >
            Data Inspection
          </a>
          <div className="mt-6 px-2 py-1 text-zinc-500">SYSTEM</div>
          <div className="px-2 py-1 text-zinc-400">v0.1.11</div>
        </aside>

        <section className="flex flex-1 flex-col overflow-auto p-4">
          {children}
        </section>
      </div>
    </main>
  );
}
