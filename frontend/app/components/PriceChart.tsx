"use client";

import { useEffect, useRef } from "react";
import { createChart, CandlestickSeries } from "lightweight-charts";

interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export default function PriceChart({ data }: { data: Candle[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "transparent" },
        textColor: "#c4c4c4",
      },
      grid: {
        vertLines: { color: "#333" },
        horzLines: { color: "#333" },
      },
      rightPriceScale: {
        borderColor: "#333",
      },
      timeScale: {
        borderColor: "#333",
        timeVisible: false,
      },
      width: containerRef.current.clientWidth,
      height: 360,
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    const sorted = [...data].sort(
      (a, b) => new Date(a.time).getTime() - new Date(b.time).getTime()
    );
    series.setData(
      sorted.map((d) => ({
        time: d.time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }))
    );
    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [data]);

  return <div ref={containerRef} className="w-full h-[360px]" />;
}
