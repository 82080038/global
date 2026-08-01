"use client"

import { useEffect } from "react"
import TerminalLayout from "../components/TerminalLayout"

export default function BacktestError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error("Backtest error:", error)
  }, [error])

  return (
    <TerminalLayout active="backtest" ticker="ERROR">
      <div className="flex h-full flex-col items-center justify-center">
        <div className="max-w-md space-y-4 text-center">
          <h1 className="text-2xl font-bold text-red-400">
            BACKTEST ERROR
          </h1>
          <div className="border border-red-500/30 bg-red-500/10 p-4 font-mono text-sm text-red-300">
            <div className="mb-2 text-red-400">ERROR DETAILS:</div>
            <div className="text-xs text-red-200">{error.message}</div>
            {error.digest && (
              <div className="mt-2 text-xs text-red-400">
                Error ID: {error.digest}
              </div>
            )}
          </div>
          <div className="space-y-2">
            <button
              onClick={reset}
              className="w-full rounded border border-green-500/30 bg-green-500/10 px-4 py-2 font-mono text-sm text-green-400 transition hover:bg-green-500/20"
            >
              [R] RETRY BACKTEST
            </button>
            <button
              onClick={() => window.location.href = "/dashboard"}
              className="w-full rounded border border-blue-500/30 bg-blue-500/10 px-4 py-2 font-mono text-sm text-blue-400 transition hover:bg-blue-500/20"
            >
              [D] RETURN TO DASHBOARD
            </button>
          </div>
        </div>
      </div>
    </TerminalLayout>
  )
}
