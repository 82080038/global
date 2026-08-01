"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  ColorType,
  CrosshairMode,
  type Time,
  type SeriesMarker,
  createSeriesMarkers,
} from "lightweight-charts";

interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  rsi?: number;
  macd?: number;
  macd_signal?: number;
  ma_20?: number;
  ma_50?: number;
  bb_upper?: number;
  bb_lower?: number;
}

interface Signal {
  time: string;
  action: "BUY" | "SELL";
  text?: string;
}

export default function PriceChart({
  data,
  signals = [],
}: {
  data: Candle[];
  signals?: Signal[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const [showIndicators, setShowIndicators] = useState(true);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    // Normalize time format: lightweight-charts expects 'yyyy-mm-dd' (no time component)
    const normalized = data.map((d) => ({
      ...d,
      time: d.time ? d.time.split("T")[0].split(" ")[0] : d.time,
    }));

    const sorted = [...normalized].sort(
      (a, b) => new Date(a.time).getTime() - new Date(b.time).getTime()
    );

    const hasRSI = sorted.some((d) => d.rsi !== undefined);
    const hasMACD = sorted.some((d) => d.macd !== undefined);

    // --- Main Chart (Candlestick + Volume + MA + Bollinger) ---
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#a1a1aa",
      },
      grid: {
        vertLines: { color: "#27272a" },
        horzLines: { color: "#27272a" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: {
        borderColor: "#3f3f46",
      },
      timeScale: {
        borderColor: "#3f3f46",
        timeVisible: false,
      },
      width: containerRef.current.clientWidth,
      height: 320,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    candleSeries.setData(
      sorted.map((d) => ({
        time: d.time as Time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }))
    );

    // MA 20 overlay
    if (sorted.some((d) => d.ma_20 !== undefined)) {
      const ma20Series = chart.addSeries(LineSeries, {
        color: "#3b82f6",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      ma20Series.setData(
        sorted
          .filter((d) => d.ma_20 !== undefined)
          .map((d) => ({ time: d.time as Time, value: d.ma_20! }))
      );
    }

    // MA 50 overlay
    if (sorted.some((d) => d.ma_50 !== undefined)) {
      const ma50Series = chart.addSeries(LineSeries, {
        color: "#f59e0b",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      ma50Series.setData(
        sorted
          .filter((d) => d.ma_50 !== undefined)
          .map((d) => ({ time: d.time as Time, value: d.ma_50! }))
      );
    }

    // Bollinger Bands
    if (sorted.some((d) => d.bb_upper !== undefined)) {
      const bbUpperSeries = chart.addSeries(LineSeries, {
        color: "#6366f1",
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      bbUpperSeries.setData(
        sorted
          .filter((d) => d.bb_upper !== undefined)
          .map((d) => ({ time: d.time as Time, value: d.bb_upper! }))
      );
    }
    if (sorted.some((d) => d.bb_lower !== undefined)) {
      const bbLowerSeries = chart.addSeries(LineSeries, {
        color: "#6366f1",
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      bbLowerSeries.setData(
        sorted
          .filter((d) => d.bb_lower !== undefined)
          .map((d) => ({ time: d.time as Time, value: d.bb_lower! }))
      );
    }

    // Volume histogram at bottom of main chart
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      color: "#3f3f46",
    });
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeries.setData(
      sorted.map((d) => ({
        time: d.time as Time,
        value: d.volume ?? 0,
        color: d.close >= d.open ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)",
      }))
    );

    // Signal markers (BUY/SELL arrows on candlestick)
    if (signals.length > 0) {
      const markers: SeriesMarker<Time>[] = signals.map((s) => ({
        time: s.time as Time,
        position: s.action === "BUY" ? "belowBar" : "aboveBar",
        color: s.action === "BUY" ? "#22c55e" : "#ef4444",
        shape: s.action === "BUY" ? "arrowUp" : "arrowDown",
        text: s.text || s.action,
      }));
      createSeriesMarkers(candleSeries, markers);
    }

    chart.timeScale().fitContent();

    // --- RSI Pane ---
    let rsiChart: ReturnType<typeof createChart> | null = null;
    if (showIndicators && hasRSI && rsiRef.current) {
      rsiChart = createChart(rsiRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: "#a1a1aa",
        },
        grid: {
          vertLines: { color: "#27272a" },
          horzLines: { color: "#27272a" },
        },
        rightPriceScale: {
          borderColor: "#3f3f46",
        },
        timeScale: {
          borderColor: "#3f3f46",
          timeVisible: false,
        },
        width: rsiRef.current.clientWidth,
        height: 100,
      });

      const rsiSeries = rsiChart.addSeries(LineSeries, {
        color: "#a855f7",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      });
      rsiSeries.setData(
        sorted
          .filter((d) => d.rsi !== undefined)
          .map((d) => ({ time: d.time as Time, value: d.rsi! }))
      );

      // Overbought/Oversold lines
      rsiSeries.createPriceLine({
        price: 70,
        color: "#ef4444",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "OB",
      });
      rsiSeries.createPriceLine({
        price: 30,
        color: "#22c55e",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "OS",
      });

      rsiChart.timeScale().fitContent();
    }

    // --- MACD Pane ---
    let macdChart: ReturnType<typeof createChart> | null = null;
    if (showIndicators && hasMACD && macdRef.current) {
      macdChart = createChart(macdRef.current, {
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: "#a1a1aa",
        },
        grid: {
          vertLines: { color: "#27272a" },
          horzLines: { color: "#27272a" },
        },
        rightPriceScale: {
          borderColor: "#3f3f46",
        },
        timeScale: {
          borderColor: "#3f3f46",
          timeVisible: false,
        },
        width: macdRef.current.clientWidth,
        height: 100,
      });

      // MACD histogram
      const macdHistSeries = macdChart.addSeries(HistogramSeries, {
        priceLineVisible: false,
        lastValueVisible: false,
      });
      macdHistSeries.setData(
        sorted
          .filter((d) => d.macd !== undefined && d.macd_signal !== undefined)
          .map((d) => {
            const hist = d.macd! - d.macd_signal!;
            return {
              time: d.time as Time,
              value: hist,
              color: hist >= 0 ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)",
            };
          })
      );

      // MACD line
      const macdLineSeries = macdChart.addSeries(LineSeries, {
        color: "#3b82f6",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      });
      macdLineSeries.setData(
        sorted
          .filter((d) => d.macd !== undefined)
          .map((d) => ({ time: d.time as Time, value: d.macd! }))
      );

      // Signal line
      const signalLineSeries = macdChart.addSeries(LineSeries, {
        color: "#f59e0b",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: true,
      });
      signalLineSeries.setData(
        sorted
          .filter((d) => d.macd_signal !== undefined)
          .map((d) => ({ time: d.time as Time, value: d.macd_signal! }))
      );

      macdChart.timeScale().fitContent();
    }

    chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
      const range = chart.timeScale().getVisibleLogicalRange();
      if (range) {
        if (rsiChart) rsiChart.timeScale().setVisibleLogicalRange(range);
        if (macdChart) macdChart.timeScale().setVisibleLogicalRange(range);
      }
    });

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
      if (rsiChart && rsiRef.current) {
        rsiChart.applyOptions({ width: rsiRef.current.clientWidth });
      }
      if (macdChart && macdRef.current) {
        macdChart.applyOptions({ width: macdRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      if (rsiChart) rsiChart.remove();
      if (macdChart) macdChart.remove();
    };
  }, [data, showIndicators, signals]);

  return (
    <div className="w-full">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[10px] font-mono text-zinc-500">
          OHLCV {data.length > 0 && `· ${data.length} bars`}
        </span>
        <button
          onClick={() => setShowIndicators(!showIndicators)}
          className="border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-[10px] font-mono text-zinc-300 hover:bg-zinc-700"
        >
          {showIndicators ? "HIDE INDICATORS" : "SHOW INDICATORS"}
        </button>
      </div>
      <div ref={containerRef} className="w-full h-[320px]" />
      {showIndicators && (
        <>
          <div className="mt-1">
            <div className="text-[10px] font-mono text-zinc-500 mb-0.5">RSI (14)</div>
            <div ref={rsiRef} className="w-full h-[100px]" />
          </div>
          <div className="mt-1">
            <div className="text-[10px] font-mono text-zinc-500 mb-0.5">MACD (12, 26, 9)</div>
            <div ref={macdRef} className="w-full h-[100px]" />
          </div>
        </>
      )}
    </div>
  );
}
