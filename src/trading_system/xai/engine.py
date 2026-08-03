"""Explainable AI Engine (Fase 5).

Menghasilkan narasi penjelasan untuk setiap rekomendasi.
Narasi menggabungkan:
- Skor multi-faktor (technical, fundamental, macro, global, relationship, sentiment)
- Breakdown detail per engine (trend, RSI, MACD, PER, PBV, ROE, DER, regime, dll.)
- Konteks foreign flow riil IDX (akumulasi/distribusi asing)
- Korelasi foreign flow vs forward return (daya prediksi)
- Lead-lag relationship antar saham IDX
- Broker concentration pasar
- Risk metrics (VaR, max drawdown, volatility)
- Manipulation detection (volume anomaly, price-volume divergence)

Sumber data:
- Tabel scores (dari DecisionEngine / AnalysisPipeline)
- Tabel foreign_flow (dari idx_batch.py, data riil IDX 2020+)
- Tabel broker_flow (dari idx_batch.py)
- Tabel ohlcv (dari Yahoo Finance / yfinance)
- analysis/manipulation.py (deteksi manipulasi pasar)
"""

from __future__ import annotations

import logging

from trading_system.data.storage import DataStorage
from trading_system.xai.advanced_context import AdvancedAnalysisProvider
from trading_system.xai.correlation_context import CorrelationContextProvider
from trading_system.xai.score_context import ScoreBreakdownProvider

logger = logging.getLogger("xai.engine")


class ExplainableAIEngine:
    name = "xai"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()
        self.ctx_provider = CorrelationContextProvider(storage)
        self.score_provider = ScoreBreakdownProvider(storage)
        self.advanced_provider = AdvancedAnalysisProvider(storage)

    def _format_flow_phase(self, phase: str) -> str:
        phases = {
            "strong_accumulation": "akumulasi asing kuat",
            "accumulation": "akumulasi asing",
            "neutral": "flow asing netral",
            "distribution": "distribusi asing",
            "strongDistribution": "distribusi asing kuat",
        }
        return phases.get(phase, phase)

    def _format_action(self, action: str) -> str:
        actions = {
            "BUY": "BELI",
            "SELL": "JUAL",
            "HOLD": "TAHAN",
            "WATCHLIST": "PANTAU",
            "AVOID": "HINDARI",
        }
        return actions.get(action, action)

    def _build_flow_narrative(self, ctx: dict, action: str) -> str:
        """Bangun narasi foreign flow."""
        if not ctx.get("available"):
            return ""

        phase = ctx["phase"]
        net_ratio = ctx["net_ratio"]
        persistence = ctx["persistence"]
        trend = ctx["trend"]
        days_pos = ctx["days_positive_10d"]
        days_total = ctx["days_total_10d"]
        net_flow = ctx["net_flow"]

        parts = []

        # Phase description
        phase_text = self._format_flow_phase(phase)
        if phase in ("strong_accumulation", "accumulation"):
            parts.append(
                f"Foreign investor sedang {phase_text} — net buy Rp {abs(net_flow)/1e9:.1f} M "
                f"dalam 20 hari terakhir (rasio net +{net_ratio:.1%}). "
                f"Persistence {persistence:.0%} ({days_pos}/{days_total} hari net buy), trend {trend}."
            )
            if action == "BUY":
                parts.append("Ini konsisten dengan rekomendasi BELI — asing akumulasi mendukung harga naik.")
            elif action == "SELL":
                parts.append(
                    "Namun rekomendasi JUAL tetap berlaku — kemungkinan skor teknikal/fundamental "
                    "menunjukkan harga sudah overbought meski asing masih beli (late accumulation)."
                )
            elif action == "HOLD":
                parts.append("Akumulasi asing mendukung HOLD — tekanan jual terbatas selama asing masih beli.")
        elif phase in ("strong_distribution", "distribution"):
            parts.append(
                f"Foreign investor sedang {phase_text} — net sell Rp {abs(net_flow)/1e9:.1f} M "
                f"dalam 20 hari terakhir (rasio net {net_ratio:.1%}). "
                f"Persistence {persistence:.0%} ({days_pos}/{days_total} hari net buy), trend {trend}."
            )
            if action == "SELL":
                parts.append("Ini memperkuat rekomendasi JUAL — distribusi asing menekan harga turun.")
            elif action == "BUY":
                parts.append(
                    "Namun rekomendasi BELI tetap diberikan — kemungkinan ada katalis fundamental "
                    "yang belum ter-refleksi di flow asing (early entry opportunity)."
                )
            elif action == "HOLD":
                parts.append("Distribusi asing menahan upside — HOLD tepat sampai flow berbalik.")
        else:
            parts.append(
                f"Foreign flow netral — net buy/sell seimbang dalam 20 hari terakhir "
                f"(rasio {net_ratio:+.1%}, persistence {persistence:.0%}). "
                f"Tidak ada tekanan asing yang signifikan ke arah tertentu."
            )

        return " ".join(parts)

    def _build_corr_narrative(self, ctx: dict) -> str:
        """Bangun narasi korelasi foreign flow vs return."""
        if not ctx.get("available"):
            return ""

        corr = ctx.get("best_corr")
        ptype = ctx.get("predictive_type")
        meaning = ctx.get("meaning")
        h = ctx.get("best_horizon", 5)

        if corr is None:
            return ""

        if ptype == "contrarian":
            return (
                f"Historis 2020-2026 menunjukkan foreign flow adalah kontra-indikator untuk saham ini "
                f"(corr {corr:+.3f} vs return {h} hari ke depan) — {meaning}. "
                f"Artinya, foreign buy justru cenderung diikuti koreksi, dan sebaliknya."
            )
        elif ptype == "confirming":
            return (
                f"Historis 2020-2026 menunjukkan foreign flow mengkonfirmasi arah harga "
                f"(corr {corr:+.3f} vs return {h} hari ke depan) — {meaning}. "
                f"Foreign buy cenderung diikuti harga naik, foreign sell diikuti turun."
            )
        else:
            return (
                f"Historis 2020-2026 menunjukkan foreign flow tidak punya daya prediksi signifikan "
                f"(corr {corr:+.3f} vs return {h} hari) — {meaning}."
            )

    def _build_lead_lag_narrative(self, ctx: dict, ticker: str) -> str:
        """Bangun narasi lead-lag."""
        if not ctx.get("available"):
            return ""

        parts = []
        code = ticker.replace(".JK", "")

        if ctx["is_leader"] and ctx["leads"]:
            followers = ctx["leads"][:3]
            follower_strs = [
                f"{f['follower'].replace('.JK','')} (lag {f['offset']}d, corr {f['corr']:+.2f})"
                for f in followers
            ]
            parts.append(
                f"{code} adalah saham LEADER — pergerakannya memprediksi "
                f"{', '.join(follower_strs)}. "
                f"Jika {code} naik hari ini, saham-saham tersebut cenderung ikut naik dalam "
                f"{followers[0]['offset']} hari ke depan."
            )

        if ctx["is_follower"] and ctx["follows"]:
            leaders = ctx["follows"][:3]
            leader_strs = [
                f"{l['leader'].replace('.JK','')} (lag {l['offset']}d, corr {l['corr']:+.2f})"
                for l in leaders
            ]
            parts.append(
                f"{code} juga FOLLOWER dari {', '.join(leader_strs)}. "
                f"Pergerakan saham-saham leader tersebut bisa dipakai sebagai early signal "
                f"untuk arah {code}."
            )

        if not parts:
            return ""

        return " ".join(parts)

    def _build_broker_narrative(self, ctx: dict) -> str:
        """Bangun narasi broker concentration."""
        if not ctx.get("available"):
            return ""

        top = ctx["top_broker"]
        share = ctx["top_share"]
        hhi = ctx["hhi_30d"]
        n = ctx["n_active_brokers"]

        if hhi > 0.6:
            conc_desc = "sangat terkonsentrasi"
        elif hhi > 0.4:
            conc_desc = "terkonsentrasi"
        else:
            conc_desc = "terdistribusi"

        return (
            f"Pasar {conc_desc} (HHI {hhi:.2f}, {n} broker aktif 30 hari). "
            f"Broker {top} mendominasi dengan {share:.1%} dari nilai transaksi terakhir "
            f"({ctx['latest_date']}). "
            f"Konsentrasi tinggi bisa mengindikasikan institutional block trading."
        )

    def _build_technical_narrative(self, ctx: dict) -> str:
        """Bangun narasi technical breakdown: trend, RSI, MACD, volume."""
        if not ctx.get("available"):
            return ""

        parts = []
        trend = ctx.get("trend", "unknown")
        rsi_level = ctx.get("rsi_level", "unknown")
        macd_signal = ctx.get("macd_signal", "unknown")

        trend_map = {"uptrend": "uptrend", "downtrend": "downtrend", "sideways": "sideways"}
        trend_id = trend_map.get(trend, trend)

        if trend_id != "unknown":
            parts.append(f"Tren harga {trend_id}")

        if rsi_level != "unknown":
            rsi_id = {"overbought": "overbought", "oversold": "oversold", "bullish": "bullish", "bearish": "bearish", "neutral": "netral"}.get(rsi_level, rsi_level)
            parts.append(f"RSI {rsi_id}")

        if macd_signal != "unknown":
            macd_id = {"bullish_cross": "MACD bullish cross", "bearish_cross": "MACD bearish cross"}.get(macd_signal, macd_signal)
            parts.append(macd_id)

        if not parts:
            return ""

        return f"Teknikal: {', '.join(parts)}."

    def _build_fundamental_narrative(self, ctx: dict) -> str:
        """Bangun narasi fundamental breakdown: PER, PBV, ROE, DER, growth."""
        if not ctx.get("available"):
            return ""

        parts = []
        components = ctx.get("components", {})
        valuation = ctx.get("valuation", "unknown")
        profitability = ctx.get("profitability", "unknown")
        leverage = ctx.get("leverage", "unknown")
        coverage = ctx.get("data_coverage", 1.0)

        if valuation != "unknown":
            val_id = {"undervalued": "undervalued", "overvalued": "overvalued", "fair": "fair value"}.get(valuation, valuation)
            parts.append(f"valuasi {val_id}")

        if profitability != "unknown":
            prof_id = {"excellent": "ROE excellent", "good": "ROE good", "average": "ROE average", "weak": "ROE weak"}.get(profitability, profitability)
            parts.append(prof_id)

        if leverage != "unknown":
            lev_id = {"low": "leverage rendah", "moderate": "leverage moderat", "high": "leverage tinggi"}.get(leverage, leverage)
            parts.append(lev_id)

        if not parts:
            return ""

        # Coverage warning
        coverage_note = ""
        if coverage < 0.6:
            missing = ctx.get("missing", [])
            coverage_note = f" (data coverage {coverage:.0%}, missing: {', '.join(missing) if missing else 'beberapa'})"

        return f"Fundamental: {', '.join(parts)}{coverage_note}."

    def _build_macro_narrative(self, ctx: dict) -> str:
        """Bangun narasi macro: regime."""
        if not ctx.get("available"):
            return ""

        regime = ctx.get("regime", "unknown")

        if regime == "unknown":
            return ""

        regime_id = {"tightening": "monetary tightening", "easing": "monetary easing", "growth": "growth phase", "slowdown": "economic slowdown"}.get(regime, regime)

        return f"Makro: regime {regime_id}."

    def _build_global_narrative(self, ctx: dict) -> str:
        """Bangun narasi global market."""
        if not ctx.get("available"):
            return ""

        health = ctx.get("market_health", "unknown")
        above_50 = ctx.get("above_50ma_pct")
        above_200 = ctx.get("above_200ma_pct")

        if health == "unknown":
            return ""

        health_id = {"strong": "global market strong", "moderate": "global market moderate", "weak": "global market weak"}.get(health, health)

        detail = ""
        if above_50 is not None and above_200 is not None:
            detail = f" ({above_50:.1f}% above 50MA, {above_200:.1f}% above 200MA)"

        return f"Global: {health_id}{detail}."

    def _build_sentiment_narrative(self, ctx: dict) -> str:
        """Bangun narasi sentiment sources."""
        if not ctx.get("available"):
            return ""

        sources = ctx.get("sources", {})
        signal = ctx.get("signal", "unknown")

        if not sources:
            return ""

        active = [k for k, v in sources.items() if v is not None]
        if not active:
            return ""

        source_map = {
            "foreign_flow": "foreign flow",
            "broker_summary": "broker summary",
            "social_media": "social media",
            "google_trends": "Google Trends",
            "news_nlp": "news NLP",
            "idx_historical": "IDX historical",
        }
        active_names = [source_map.get(k, k) for k in active]

        signal_id = {"bullish": "bullish", "bearish": "bearish", "neutral": "netral"}.get(signal, signal)

        return f"Sentiment: sumber aktif {', '.join(active_names)}, sinyal {signal_id}."

    def _build_risk_narrative(self, ctx: dict) -> str:
        """Bangun narasi risk metrics: VaR, drawdown, volatility."""
        if not ctx.get("available"):
            return ""

        parts = []
        var_95 = ctx.get("var_95_1d")
        max_dd = ctx.get("max_drawdown")
        vol_level = ctx.get("volatility_level")
        risk_flags = ctx.get("risk_flags", [])

        if var_95 is not None:
            parts.append(f"VaR 95% 1-day {var_95:.2f}%")
        if max_dd is not None:
            parts.append(f"max drawdown {max_dd:.1f}%")
        if vol_level == "high":
            parts.append("volatilitas tinggi")

        if not parts and not risk_flags:
            return ""

        risk_str = ", ".join(parts)
        flags_str = f" [{', '.join(risk_flags)}]" if risk_flags else ""

        return f"Risk: {risk_str}{flags_str}."

    def _build_manipulation_narrative(self, ctx: dict) -> str:
        """Bangun narasi manipulation detection."""
        if not ctx.get("available"):
            return ""

        total = ctx.get("total_flags", 0)
        high_count = ctx.get("high_severity_count", 0)
        has_danger = ctx.get("has_danger", False)

        if total == 0:
            return ""

        flags = ctx.get("flags", [])
        flag_details = [f"{f['check']} ({f['severity']})" for f in flags[:3]]

        if has_danger:
            return (
                f"PERINGATAN MANIPULASI: {total} flag terdeteksi ({high_count} high severity) — "
                f"{', '.join(flag_details)}. Hati-hati eksekusi order."
            )
        else:
            return f"Manipulation check: {total} flag minor — {', '.join(flag_details)}."

    def _build_enhanced_regime_narrative(self, ctx: dict) -> str:
        """Bangun narasi enhanced regime (risk_on/risk_off/neutral)."""
        if not ctx.get("available"):
            return ""

        regime = ctx.get("regime", "unknown")
        confidence = ctx.get("confidence", 0.0)
        score = ctx.get("score", 0.0)
        top_components = ctx.get("top_components", [])

        regime_id = {"risk_on": "RISK ON", "risk_off": "RISK OFF", "neutral": "NEUTRAL"}.get(regime, regime)

        parts = [f"Regime global {regime_id} (confidence {confidence:.0%}, z-score {score:+.2f})"]

        if top_components:
            comp_strs = []
            for c in top_components[:2]:
                comp_strs.append(f"{c.get('key', '?')} z={c.get('z', 0):+.2f}")
            parts.append(f"driver: {', '.join(comp_strs)}")

        return f"Enhanced regime: {'. '.join(parts)}."

    def _build_cross_asset_narrative(self, ctx: dict) -> str:
        """Bangun narasi cross-asset."""
        if not ctx.get("available"):
            return ""

        regime = ctx.get("regime", "unknown")
        confidence = ctx.get("confidence", 0.0)
        risk_on = ctx.get("risk_on_votes", 0)
        risk_off = ctx.get("risk_off_votes", 0)
        strongest = ctx.get("strongest_pairs", [])

        parts = [f"cross-asset regime {regime} (on:{risk_on}/off:{risk_off}, consistency {confidence:.0%})"]

        if strongest:
            pair_strs = []
            for p in strongest[:2]:
                pair_strs.append(f"{p.get('label', '?')} corr={p.get('correlation', 0):+.2f}")
            parts.append(f"strongest: {', '.join(pair_strs)}")

        return f"Cross-asset: {'. '.join(parts)}."

    def _build_pattern_reliability_narrative(self, ctx: dict) -> str:
        """Bangun narasi pattern reliability."""
        if not ctx.get("available"):
            return ""

        patterns = ctx.get("patterns", 0)
        top_patterns = ctx.get("top_patterns", [])

        if patterns == 0:
            return ""

        parts = [f"{patterns} pola historis terverifikasi"]

        if top_patterns:
            pat_strs = []
            for p in top_patterns[:3]:
                pat_strs.append(
                    f"{p['pattern']} (win-rate {p['win_rate']:.0f}%, "
                    f"avg return 5d {p['avg_return_5d']:+.1f}%, rating {p['rating']})"
                )
            parts.append(f"top: {', '.join(pat_strs)}")

        return f"Pattern reliability: {'. '.join(parts)}."

    def _build_no_trade_narrative(self, ctx: dict) -> str:
        """Bangun narasi no-trade gate."""
        if not ctx.get("available"):
            return ""

        decision = ctx.get("decision", "PROCEED")
        gates_failed = ctx.get("gates_failed", [])
        reason_codes = ctx.get("reason_codes", [])

        if decision == "PROCEED" and not gates_failed:
            return ""

        if decision == "NO_TRADE":
            return (
                f"PERINGATAN NO-TRADE: {len(gates_failed)} gate gagal — "
                f"{', '.join(gates_failed)}. {'; '.join(reason_codes[:2])}. "
                f"Pertimbangkan untuk tidak eksekusi."
            )

        return ""

    def _build_factor_narrative(self, ctx: dict) -> str:
        """Bangun narasi factor ranking."""
        if not ctx.get("available"):
            return ""

        composite = ctx.get("composite_rank")
        factors = ctx.get("factors", [])
        universe = ctx.get("universe_size", 0)

        if not factors:
            return ""

        # Top and bottom factor
        top_factor = factors[0]
        bottom_factor = factors[-1]

        parts = []
        if composite is not None:
            parts.append(f"composite rank {composite:.2f} dari {universe} saham")

        top_name = top_factor.get("factor", "?")
        top_pct = top_factor.get("percentile_rank", 0.5)
        parts.append(f"faktor terkuat {top_name} (persentil {top_pct:.0%})")

        bot_name = bottom_factor.get("factor", "?")
        bot_pct = bottom_factor.get("percentile_rank", 0.5)
        parts.append(f"terlemah {bot_name} (persentil {bot_pct:.0%})")

        return f"Factor: {', '.join(parts)}."

    def _build_counter_scenarios(self, ticker: str, flow_ctx: dict, corr_ctx: dict) -> list[str]:
        """Bangun counter-scenario berdasarkan konteks."""
        scenarios = []

        if flow_ctx.get("available") and flow_ctx["phase"] in ("accumulation", "strong_accumulation"):
            scenarios.append(
                "Jika foreign flow berbalik menjadi net sell >Rp 50 M/hari, "
                "rekomendasi bisa turun ke HOLD/SELL — monitor foreign_flow harian."
            )
        elif flow_ctx.get("available") and flow_ctx["phase"] in ("distribution", "strong_distribution"):
            scenarios.append(
                f"Jika foreign flow berbalik menjadi net buy, ini bisa menjadi sinyal reversal — "
                f"monitor perubahan persistence dari {flow_ctx['persistence']:.0%}."
            )

        if corr_ctx.get("available") and corr_ctx.get("predictive_type") == "contrarian":
            scenarios.append(
                f"Karena foreign flow bersifat kontra-indikator untuk {ticker.replace('.JK','')}, "
                f"foreign buy justru bisa menjadi sinyal untuk take profit."
            )

        if corr_ctx.get("available") and corr_ctx.get("predictive_type") == "confirming":
            scenarios.append(
                "Jika foreign flow tiba-tiba berbalik arah berlawanan dari rekomendasi, "
                "validasi ulang — historis flow mengkonfirmasi arah harga."
            )

        # Default scenarios
        if not scenarios:
            scenarios.append("Jika USD/IDR melemah 5%, fundamental score bisa turun dan stop loss perlu diperketat.")
            scenarios.append("Jika IHSG tumbuh 2% dalam seminggu, conviction bisa naik ke level BUY.")

        return scenarios

    def explain(self, ticker: str, recommendation: dict | None = None) -> dict:
        if recommendation is None:
            return {"status": "error", "message": "recommendation dict required"}

        action = recommendation.get("action")
        conviction = recommendation.get("conviction_score", 0)
        scores = recommendation.get("contributing_scores", {})
        risk_flags = recommendation.get("risk_flags", [])

        # Faktor paling memengaruhi
        sorted_scores = sorted(scores.items(), key=lambda x: x[1] or 0, reverse=True)
        top_factor = sorted_scores[0][0] if sorted_scores else "unknown"
        bottom_factor = sorted_scores[-1][0] if sorted_scores else "unknown"

        # Confidence interval
        confidence_low = max(0, conviction - 10)
        confidence_high = min(100, conviction + 10)

        # Correlation context (IDX data)
        flow_ctx = self.ctx_provider.get_foreign_flow_context(ticker)
        corr_ctx = self.ctx_provider.get_flow_return_correlation(ticker)
        ll_ctx = self.ctx_provider.get_lead_lag_context(ticker)
        broker_ctx = self.ctx_provider.get_broker_context()

        # Score breakdown context (per-engine detail)
        score_ctxs = self.score_provider.get_all_contexts(ticker, recommendation)
        tech_ctx = score_ctxs.get("technical", {})
        fund_ctx = score_ctxs.get("fundamental", {})
        macro_ctx = score_ctxs.get("macro", {})
        global_ctx = score_ctxs.get("global", {})
        rel_ctx = score_ctxs.get("relationship", {})
        sent_ctx = score_ctxs.get("sentiment", {})
        risk_ctx = score_ctxs.get("risk", {})
        manip_ctx = score_ctxs.get("manipulation", {})

        # Build narrative
        action_id = self._format_action(action)
        narrative_parts = [
            f"Rekomendasi {action_id} untuk {ticker} dibentuk dengan conviction {conviction:.1f} "
            f"(interval {confidence_low:.0f}-{confidence_high:.0f}). "
            f"Faktor paling mendukung adalah {top_factor} (score: {scores.get(top_factor)}). "
            f"Faktor paling menahan adalah {bottom_factor} (score: {scores.get(bottom_factor)})."
        ]

        # Score breakdown narratives
        tech_n = self._build_technical_narrative(tech_ctx)
        if tech_n:
            narrative_parts.append(tech_n)

        fund_n = self._build_fundamental_narrative(fund_ctx)
        if fund_n:
            narrative_parts.append(fund_n)

        macro_n = self._build_macro_narrative(macro_ctx)
        if macro_n:
            narrative_parts.append(macro_n)

        global_n = self._build_global_narrative(global_ctx)
        if global_n:
            narrative_parts.append(global_n)

        sent_n = self._build_sentiment_narrative(sent_ctx)
        if sent_n:
            narrative_parts.append(sent_n)

        # Correlation & flow narratives (IDX data)
        flow_n = self._build_flow_narrative(flow_ctx, action)
        if flow_n:
            narrative_parts.append(flow_n)

        corr_n = self._build_corr_narrative(corr_ctx)
        if corr_n:
            narrative_parts.append(corr_n)

        ll_n = self._build_lead_lag_narrative(ll_ctx, ticker)
        if ll_n:
            narrative_parts.append(ll_n)

        broker_n = self._build_broker_narrative(broker_ctx)
        if broker_n:
            narrative_parts.append(broker_n)

        # Risk & manipulation narratives
        risk_n = self._build_risk_narrative(risk_ctx)
        if risk_n:
            narrative_parts.append(risk_n)

        manip_n = self._build_manipulation_narrative(manip_ctx)
        if manip_n:
            narrative_parts.append(manip_n)

        # Advanced engine contexts
        macro_regime = macro_ctx.get("regime", "neutral")
        adv_ctxs = self.advanced_provider.get_all_contexts(ticker, conviction, macro_regime)
        regime_ctx = adv_ctxs.get("enhanced_regime", {})
        crossasset_ctx = adv_ctxs.get("cross_asset", {})
        pattern_ctx = adv_ctxs.get("pattern_reliability", {})
        notrade_ctx = adv_ctxs.get("no_trade", {})
        factor_ctx = adv_ctxs.get("factor", {})

        regime_n = self._build_enhanced_regime_narrative(regime_ctx)
        if regime_n:
            narrative_parts.append(regime_n)

        crossasset_n = self._build_cross_asset_narrative(crossasset_ctx)
        if crossasset_n:
            narrative_parts.append(crossasset_n)

        pattern_n = self._build_pattern_reliability_narrative(pattern_ctx)
        if pattern_n:
            narrative_parts.append(pattern_n)

        factor_n = self._build_factor_narrative(factor_ctx)
        if factor_n:
            narrative_parts.append(factor_n)

        notrade_n = self._build_no_trade_narrative(notrade_ctx)
        if notrade_n:
            narrative_parts.append(notrade_n)

        narrative = " ".join(narrative_parts)

        # Counter scenarios berbasis konteks
        scenarios = self._build_counter_scenarios(ticker, flow_ctx, corr_ctx)

        # Add manipulation-based scenarios
        if manip_ctx.get("has_danger"):
            scenarios.append(
                "Manipulation detection menemukan high-severity flag — "
                "pertimbangkan menunda eksekusi atau reduce position size."
            )

        # Add no-trade scenarios
        if notrade_ctx.get("decision") == "NO_TRADE":
            gates = notrade_ctx.get("gates_failed", [])
            scenarios.append(
                f"No-Trade gate aktif ({', '.join(gates)}) — "
                f"pertimbangkan skip eksekusi sampai gate terpenuhi."
            )

        # Add regime-based scenarios
        if regime_ctx.get("available") and regime_ctx.get("regime") == "risk_off":
            scenarios.append(
                "Regime global RISK OFF — jika berlanjut, tekanan jual bisa meningkat "
                "dan rekomendasi BUY perlu dievaluasi ulang."
            )

        explanation = {
            "status": "ok",
            "ticker": ticker,
            "action": action,
            "narrative": narrative,
            "top_factors": sorted_scores[:3],
            "confidence_interval": [round(confidence_low, 2), round(confidence_high, 2)],
            "risk_summary": risk_flags if risk_flags else ["No critical risk flags"],
            "counter_scenarios": scenarios,
            "context": {
                "foreign_flow": flow_ctx,
                "flow_return_correlation": corr_ctx,
                "lead_lag": ll_ctx,
                "broker_concentration": broker_ctx,
                "technical": tech_ctx,
                "fundamental": fund_ctx,
                "macro": macro_ctx,
                "global": global_ctx,
                "relationship": rel_ctx,
                "sentiment": sent_ctx,
                "risk": risk_ctx,
                "manipulation": manip_ctx,
                "enhanced_regime": regime_ctx,
                "cross_asset": crossasset_ctx,
                "pattern_reliability": pattern_ctx,
                "no_trade": notrade_ctx,
                "factor": factor_ctx,
            },
        }
        return explanation
