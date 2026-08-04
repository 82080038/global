import { useState } from "react";
import { Outlet, NavLink, useLocation } from "react-router-dom";

export default function Layout() {
  const [time, setTime] = useState(() => new Date().toLocaleTimeString("id-ID"));
  const location = useLocation();

  // Update clock
  useState(() => {
    const interval = setInterval(() => setTime(new Date().toLocaleTimeString("id-ID")), 1000);
    return () => clearInterval(interval);
  });

  return (
    <main className="flex h-screen flex-col bg-zinc-950 text-zinc-100 font-mono">
      <header className="flex items-center border-b border-zinc-800 bg-black px-4 py-1.5 text-xs">
        <NavLink to="/test" className="font-bold text-green-400 mr-4">
          TS-TEST
        </NavLink>
        <div className="flex gap-4 text-zinc-500">
          <span className="text-green-400">●</span>
          <span>PREDICTION ACCURACY HARNESS</span>
          <span>v0.1.11</span>
        </div>
        <div className="ml-auto flex items-center gap-4 text-zinc-500">
          <span>{time}</span>
          <span className="text-zinc-700">│</span>
          <NavLink
            to="/test"
            className={({ isActive }) =>
              isActive ? "text-green-400" : "text-zinc-500 hover:text-zinc-300"
            }
          >
            CONSOLE
          </NavLink>
        </div>
      </header>

      <section className="flex flex-1 overflow-hidden">
        <Outlet />
      </section>
    </main>
  );
}
