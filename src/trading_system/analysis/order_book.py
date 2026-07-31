"""Order Book Analyzer — Gap detection and Support/Resistance identification.

Component U — adopted from trading-otomatis-indonesia (raw copy).
Pure pandas/numpy, no external dependencies.

Concepts:
1. Price gap detection — identify gaps > threshold between candles
2. Volume gap detection — identify volume changes > threshold
3. Support/Resistance identification — levels tested >= 3x with 1% tolerance
4. Gap strength scoring — measure gap strength based on ratio
5. Market efficiency — fewer gaps = more efficient
6. Gap fill predictions — gaps tend to fill toward equilibrium
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class OrderBookAnalyzer:
    """Order Book Analyzer — gap and pattern analysis from order book concepts."""

    def __init__(self, gap_threshold: float = 0.02, volume_threshold: float = 0.5):
        self.gap_threshold = gap_threshold
        self.volume_threshold = volume_threshold

    def detect_price_gaps(self, data: pd.DataFrame) -> list[dict]:
        """Detect price gaps between consecutive candles."""
        gaps = []
        for i in range(1, len(data)):
            current_price = data.iloc[i]["close"]
            previous_price = data.iloc[i - 1]["close"]
            gap_ratio = abs(current_price - previous_price) / previous_price

            if gap_ratio > self.gap_threshold:
                gap_direction = "UP" if current_price > previous_price else "DOWN"
                gaps.append({
                    "index": i,
                    "date": data.iloc[i]["date"] if "date" in data.columns else i,
                    "previous_price": float(previous_price),
                    "current_price": float(current_price),
                    "gap_ratio": float(gap_ratio),
                    "direction": gap_direction,
                    "gap_strength": float(gap_ratio),
                })
        return gaps

    def detect_volume_gaps(self, data: pd.DataFrame) -> list[dict]:
        """Detect volume gaps between consecutive candles."""
        volume_gaps = []
        for i in range(1, len(data)):
            current_volume = data.iloc[i]["volume"]
            previous_volume = data.iloc[i - 1]["volume"]

            if previous_volume > 0:
                volume_gap_ratio = abs(current_volume - previous_volume) / previous_volume
                if volume_gap_ratio > self.volume_threshold:
                    volume_direction = "INCREASE" if current_volume > previous_volume else "DECREASE"
                    volume_gaps.append({
                        "index": i,
                        "date": data.iloc[i]["date"] if "date" in data.columns else i,
                        "previous_volume": float(previous_volume),
                        "current_volume": float(current_volume),
                        "volume_gap_ratio": float(volume_gap_ratio),
                        "direction": volume_direction,
                        "volume_strength": float(volume_gap_ratio),
                    })
        return volume_gaps

    def identify_support_resistance_levels(self, data: pd.DataFrame, window: int = 20) -> dict:
        """Identify support and resistance levels tested >= 3x with 1% tolerance."""
        lows = data["low"].values
        highs = data["high"].values

        support_levels = []
        resistance_levels = []

        for i in range(window, len(lows) - window):
            window_lows = lows[i - window : i + window]
            current_low = lows[i]
            touches = int(np.sum(np.abs(window_lows - current_low) < (current_low * 0.01)))
            if touches >= 3:
                support_levels.append({
                    "level": float(current_low),
                    "touches": touches,
                    "strength": touches / len(window_lows),
                    "index": i,
                })

        for i in range(window, len(highs) - window):
            window_highs = highs[i - window : i + window]
            current_high = highs[i]
            touches = int(np.sum(np.abs(window_highs - current_high) < (current_high * 0.01)))
            if touches >= 3:
                resistance_levels.append({
                    "level": float(current_high),
                    "touches": touches,
                    "strength": touches / len(window_highs),
                    "index": i,
                })

        support_levels.sort(key=lambda x: x["strength"], reverse=True)
        resistance_levels.sort(key=lambda x: x["strength"], reverse=True)

        return {
            "support_levels": support_levels[:10],
            "resistance_levels": resistance_levels[:10],
        }

    def calculate_market_efficiency(self, data: pd.DataFrame) -> float:
        """Calculate market efficiency score (0-1, higher = more efficient)."""
        try:
            prices = data["close"].values
            volumes = data["volume"].values

            price_changes = np.abs(np.diff(prices))
            volatility = np.std(price_changes)

            volume_changes = np.abs(np.diff(volumes))
            volume_volatility = np.std(volume_changes)

            price_gaps = self.detect_price_gaps(data)
            volume_gaps = self.detect_volume_gaps(data)

            gap_ratio = (len(price_gaps) + len(volume_gaps)) / len(data)
            volatility_score = 1 - min(volatility / np.mean(prices), 1)
            volume_score = 1 - min(volume_volatility / np.mean(volumes), 1)

            efficiency = (volatility_score + volume_score + (1 - gap_ratio)) / 3
            return max(0, min(1, float(efficiency)))
        except Exception:
            return 0.5

    def analyze_pattern_formation(self, data: pd.DataFrame) -> dict:
        """Analyze pattern formation based on gaps and levels."""
        try:
            price_gaps = self.detect_price_gaps(data)
            volume_gaps = self.detect_volume_gaps(data)
            levels = self.identify_support_resistance_levels(data)

            pattern_count = len(price_gaps) + len(volume_gaps) + len(levels["support_levels"]) + len(levels["resistance_levels"])
            gap_strength = float(np.mean([g["gap_strength"] for g in price_gaps])) if price_gaps else 0
            volume_strength = float(np.mean([g["volume_strength"] for g in volume_gaps])) if volume_gaps else 0

            return {
                "pattern_count": pattern_count,
                "gap_strength": gap_strength,
                "volume_strength": volume_strength,
                "total_strength": (gap_strength + volume_strength) / 2,
            }
        except Exception:
            return {"pattern_count": 0, "gap_strength": 0, "volume_strength": 0, "total_strength": 0}

    def generate_order_book_signals(
        self, data: pd.DataFrame, price_gaps: list, volume_gaps: list, levels: dict
    ) -> dict:
        """Generate trading signals based on order book analysis."""
        try:
            current_volume = data["volume"].iloc[-1]
            avg_volume = data["volume"].rolling(20).mean().iloc[-1]

            recent_gaps = [g for g in price_gaps if g["index"] >= len(data) - 5]
            recent_volume_gaps = [g for g in volume_gaps if g["index"] >= len(data) - 5]

            signal = "HOLD"
            confidence = 0.3
            reason = "No strong order book signals"

            if recent_gaps:
                latest_gap = recent_gaps[-1]
                if latest_gap["direction"] == "UP" and latest_gap["gap_strength"] > 0.05:
                    signal = "BUY"
                    confidence = min(0.8, latest_gap["gap_strength"] * 2)
                    reason = f'Strong upward gap detected: {latest_gap["gap_strength"]:.2%}'
                elif latest_gap["direction"] == "DOWN" and latest_gap["gap_strength"] > 0.05:
                    signal = "SELL"
                    confidence = min(0.8, latest_gap["gap_strength"] * 2)
                    reason = f'Strong downward gap detected: {latest_gap["gap_strength"]:.2%}'

            if recent_volume_gaps and signal != "HOLD":
                volume_gap = recent_volume_gaps[-1]
                if volume_gap["direction"] == "INCREASE":
                    confidence = min(0.9, confidence + 0.2)
                    reason += " + Volume confirmation"

            return {
                "signal": signal,
                "confidence": float(confidence),
                "reason": reason,
                "gap_count": len(recent_gaps),
                "volume_gap_count": len(recent_volume_gaps),
            }
        except Exception:
            return {"signal": "HOLD", "confidence": 0.3, "reason": "Error in signal generation", "gap_count": 0, "volume_gap_count": 0}

    def analyze_order_book(self, data: pd.DataFrame) -> dict:
        """Comprehensive order book analysis — main entry point."""
        try:
            price_gaps = self.detect_price_gaps(data)
            volume_gaps = self.detect_volume_gaps(data)
            levels = self.identify_support_resistance_levels(data)
            efficiency_score = self.calculate_market_efficiency(data)
            pattern_analysis = self.analyze_pattern_formation(data)
            signals = self.generate_order_book_signals(data, price_gaps, volume_gaps, levels)

            return {
                "gap_count": len(price_gaps),
                "volume_gap_count": len(volume_gaps),
                "pattern_count": pattern_analysis["pattern_count"],
                "efficiency_score": efficiency_score,
                "support_levels": len(levels["support_levels"]),
                "resistance_levels": len(levels["resistance_levels"]),
                "price_gaps": price_gaps,
                "volume_gaps": volume_gaps,
                "support_resistance": levels,
                "pattern_analysis": pattern_analysis,
                "signals": signals,
                "analysis_timestamp": pd.Timestamp.now().isoformat(),
            }
        except Exception as e:
            return {
                "error": str(e),
                "gap_count": 0,
                "volume_gap_count": 0,
                "pattern_count": 0,
                "efficiency_score": 0.5,
                "support_levels": 0,
                "resistance_levels": 0,
                "analysis_timestamp": pd.Timestamp.now().isoformat(),
            }

    def analyze_market_efficiency(self, data: pd.DataFrame) -> dict:
        """Detailed market efficiency analysis."""
        prices = data["close"].values
        volumes = data["volume"].values

        price_changes = np.abs(np.diff(prices))
        volatility = np.std(price_changes)

        volume_changes = np.abs(np.diff(volumes))
        volume_volatility = np.std(volume_changes)

        price_gaps = self.detect_price_gaps(data)
        volume_gaps = self.detect_volume_gaps(data)

        gap_frequency = (len(price_gaps) + len(volume_gaps)) / len(data)
        efficiency_score = 1 / (1 + volatility + gap_frequency)
        pattern_density = gap_frequency + (volatility / np.mean(prices))

        return {
            "efficiency_score": float(efficiency_score),
            "volatility": float(volatility),
            "volume_volatility": float(volume_volatility),
            "gap_frequency": float(gap_frequency),
            "pattern_density": float(pattern_density),
            "price_gap_count": len(price_gaps),
            "volume_gap_count": len(volume_gaps),
        }

    def detect_pattern_blocks(self, data: pd.DataFrame) -> list[dict]:
        """Detect pattern blocks — gaps combined with volume context."""
        patterns = []
        price_gaps = self.detect_price_gaps(data)
        volume_gaps = self.detect_volume_gaps(data)

        for price_gap in price_gaps:
            pattern = {
                "type": "GAP_PATTERN",
                "index": price_gap["index"],
                "date": price_gap["date"],
                "price_gap": price_gap,
                "volume_gap": None,
                "pattern_strength": price_gap["gap_strength"],
            }
            for volume_gap in volume_gaps:
                if abs(volume_gap["index"] - price_gap["index"]) <= 1:
                    pattern["volume_gap"] = volume_gap
                    pattern["pattern_strength"] = (price_gap["gap_strength"] + volume_gap["volume_strength"]) / 2
                    break
            patterns.append(pattern)

        levels = self.identify_support_resistance_levels(data)
        for support in levels["support_levels"]:
            patterns.append({
                "type": "SUPPORT_PATTERN",
                "index": support["index"],
                "level": support["level"],
                "strength": support["strength"],
                "pattern_strength": support["strength"],
            })
        for resistance in levels["resistance_levels"]:
            patterns.append({
                "type": "RESISTANCE_PATTERN",
                "index": resistance["index"],
                "level": resistance["level"],
                "strength": resistance["strength"],
                "pattern_strength": resistance["strength"],
            })

        patterns.sort(key=lambda x: x["pattern_strength"], reverse=True)
        return patterns

    def calculate_pattern_probability(self, data: pd.DataFrame, lookback: int = 30) -> dict:
        """Calculate pattern probability based on historical data."""
        recent_data = data.tail(lookback)
        patterns = self.detect_pattern_blocks(recent_data)
        efficiency = self.analyze_market_efficiency(recent_data)

        total_patterns = len(patterns)
        strong_patterns = len([p for p in patterns if p["pattern_strength"] > 0.5])
        pattern_probability = strong_patterns / total_patterns if total_patterns > 0 else 0
        next_pattern_probability = pattern_probability * (1 - efficiency["efficiency_score"])

        return {
            "pattern_probability": float(pattern_probability),
            "next_pattern_probability": float(next_pattern_probability),
            "total_patterns": total_patterns,
            "strong_patterns": strong_patterns,
            "efficiency_impact": 1 - efficiency["efficiency_score"],
        }

    def generate_gap_fill_predictions(self, data: pd.DataFrame) -> list[dict]:
        """Generate gap fill predictions — gaps tend to fill toward equilibrium."""
        predictions = []
        price_gaps = self.detect_price_gaps(data)
        if not price_gaps:
            return predictions

        latest_gap = price_gaps[-1]
        current_price = data["close"].iloc[-1]

        if latest_gap["direction"] == "UP":
            fill_target = latest_gap["previous_price"]
            fill_probability = min(1.0, latest_gap["gap_ratio"] * 2)
            predictions.append({
                "type": "GAP_FILL_DOWN",
                "target_price": float(fill_target),
                "probability": float(fill_probability),
                "gap_size": latest_gap["gap_ratio"],
                "current_price": float(current_price),
            })
        elif latest_gap["direction"] == "DOWN":
            fill_target = latest_gap["previous_price"]
            fill_probability = min(1.0, latest_gap["gap_ratio"] * 2)
            predictions.append({
                "type": "GAP_FILL_UP",
                "target_price": float(fill_target),
                "probability": float(fill_probability),
                "gap_size": latest_gap["gap_ratio"],
                "current_price": float(current_price),
            })
        return predictions

    def comprehensive_analysis(self, data: pd.DataFrame) -> dict:
        """Full analysis combining all order book concepts."""
        price_gaps = self.detect_price_gaps(data)
        volume_gaps = self.detect_volume_gaps(data)
        levels = self.identify_support_resistance_levels(data)
        efficiency = self.analyze_market_efficiency(data)
        patterns = self.detect_pattern_blocks(data)
        probabilities = self.calculate_pattern_probability(data)
        gap_predictions = self.generate_gap_fill_predictions(data)

        return {
            "price_gaps": price_gaps,
            "volume_gaps": volume_gaps,
            "support_levels": levels["support_levels"],
            "resistance_levels": levels["resistance_levels"],
            "market_efficiency": efficiency,
            "patterns": patterns,
            "probabilities": probabilities,
            "gap_predictions": gap_predictions,
            "summary": {
                "total_gaps": len(price_gaps) + len(volume_gaps),
                "pattern_count": len(patterns),
                "efficiency_score": efficiency["efficiency_score"],
                "pattern_probability": probabilities["pattern_probability"],
            },
        }
