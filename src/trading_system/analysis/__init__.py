"""Analysis layer: feature engineering & indicator computation.

This layer processes raw data into actionable indicators and factors:
- Technical indicators (MA, RSI, MACD, etc.)
- Fundamental analysis (PE, PBV, etc.)
- Macro analysis (regime detection, interest rates)
- Global market analysis (cross-asset correlation, lead-lag)
- Market relationship analysis (correlation, lag analysis)

Output: Computed indicators and factors used by decision engine.
"""
