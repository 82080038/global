"""News & Sentiment Engine (Fase 3) — NLP untuk berita Indonesia.

Mengambil berita dari RSS feed sumber Indonesia (Bisnis.com, Kontan, CNBC Indonesia),
lalu melakukan sentiment analysis menggunakan Indonesian lexicon-based approach.

Jika tidak ada berita tersedia, fallback ke proxy sentimen dari price & volume.
"""

from __future__ import annotations

import re
import logging

import numpy as np
import pandas as pd

from trading_system.data.storage import DataStorage

logger = logging.getLogger("sentiment")

# Indonesian sentiment lexicon (positive & negative words).
# NOTE: kata netral/ambigu ("volume", "transaksi", "target", "konsolidasi") sengaja
# dihapus dari POSITIVE_WORDS karena tidak inheren positif dan membias skor ke atas.
# "rugi" HANYA masuk NEGATIVE_WORDS (jelas kata negatif) — sebelumnya juga ada di
# POSITIVE_WORDS sehingga saling menetralkan skor berita yang menyebut "rugi".
POSITIVE_WORDS = {
    "naik", "tinggi", "untung", "positif", "bullish", "beli", "kuat",
    "tumbuh", "unggul", "optimis", "rally", "gain", "profit", "dividen",
    "akuisisi", "ekspansi", "investasi", "surplus", "rekomen",
    "mendukung", "meningkat", "melonjak", "menguat", "meroket", "rebound",
    "penguatan", "peluang", "sukses",
    "akumulasi", "hold", "outperform", "upgrade", "potensial",
    "stabil", "recover", "pemulihan", "kontrak", "order",
}

NEGATIVE_WORDS = {
    "turun", "rugi", "negatif", "bearish", "jual", "lemah", "jatuh", "kerugian",
    "anjlok", "melemah", "tertekan", "koreksi", "penurunan", "terjun", "loss",
    "sell", "dump", "crash", "bocor", "fraud", "skandal", "gagal", "bangkrut",
    "pailit", "default", "risiko", "ancaman", "tekanan", "kelemahan", "merosot",
    "terpuruk", "pelemahan", "pelarian", "panik", "kapitulasi", "downgrade",
    "utang", "macet", "npl", "suspensi", "delisting", "peringatan",
    "pelanggaran", "denda", "sanksi", "turunkan", "membenamkan", "terendah",
}

assert POSITIVE_WORDS & NEGATIVE_WORDS == set(), "Lexicon overlap: kata tidak boleh ada di kedua daftar"

# Negation words: membalik polaritas kata sentimen berikutnya (mis. "tidak untung").
NEGATION_WORDS = {"tidak", "bukan", "belum", "tanpa", "jangan", "kurang"}

# RSS feeds for Indonesian financial news
RSS_FEEDS = [
    "https://www.bisnis.com/rss/markets",
    "https://www.kontan.co.id/rss/investasi",
    "https://www.cnbcindonesia.com/market/rss",
]


class SentimentEngine:
    name = "sentiment"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    def _fetch_news(self, ticker: str, max_items: int = 20) -> list[dict]:
        """Fetch recent news from RSS feeds, filter by ticker keywords."""
        try:
            import feedparser
        except ImportError:
            logger.warning("feedparser not installed, skipping RSS fetch")
            return []

        # Extract company name from ticker (e.g. BBCA.JK -> BBCA)
        keyword = ticker.replace(".JK", "").lower()
        company_names = self._get_company_aliases(keyword)

        articles = []
        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:50]:
                    title = entry.get("title", "")
                    summary = entry.get("summary", entry.get("description", ""))
                    text = f"{title} {summary}".lower()

                    # Check if any keyword matches
                    if any(kw in text for kw in company_names):
                        articles.append({
                            "title": title,
                            "summary": summary,
                            "published": entry.get("published", ""),
                            "link": entry.get("link", ""),
                        })
                        if len(articles) >= max_items:
                            break
            except Exception as e:
                logger.debug(f"RSS feed error ({feed_url}): {e}")

        return articles

    def _get_company_aliases(self, ticker_code: str) -> list[str]:
        """Map ticker code to searchable keywords."""
        aliases = {
            "bbca": ["bbca", "bank central asia", "bca"],
            "tlkm": ["tlkm", "telkom", "telekomunikasi"],
            "asii": ["asii", "astra", "astra international"],
            "unvr": ["unvr", "unilever"],
            "ggrm": ["ggrm", "gudang garam"],
            "bmri": ["bmri", "mandiri", "bank mandiri"],
            "bbri": ["bbri", "bri", "bank rakyat"],
            "icbp": ["icbp", "indofood cbp", "indofood"],
            "adro": ["adro", "adaro"],
            "mdka": ["mdka", "merdeka"],
        }
        return aliases.get(ticker_code, [ticker_code])

    def _analyze_text(self, text: str) -> float:
        """Analyze sentiment of a text using Indonesian lexicon.

        Returns sentiment score from -1.0 (very negative) to 1.0 (very positive).
        """
        text_lower = text.lower()
        # Tokenize: split on non-alphanumeric
        tokens = re.findall(r"[a-z]+", text_lower)

        if not tokens:
            return 0.0

        pos_count = 0
        neg_count = 0
        for i, t in enumerate(tokens):
            # Negasi: kata negasi dalam jendela 2 token sebelumnya membalik polaritas
            negated = any(tokens[j] in NEGATION_WORDS for j in range(max(0, i - 2), i))
            if t in POSITIVE_WORDS:
                if negated:
                    neg_count += 1
                else:
                    pos_count += 1
            elif t in NEGATIVE_WORDS:
                if negated:
                    pos_count += 1
                else:
                    neg_count += 1

        total = pos_count + neg_count
        if total == 0:
            return 0.0

        return (pos_count - neg_count) / total

    def _news_sentiment(self, ticker: str) -> dict | None:
        """Compute sentiment from news articles. Returns None if no news."""
        articles = self._fetch_news(ticker)
        if not articles:
            return None

        scores = []
        for article in articles:
            text = f"{article['title']} {article['summary']}"
            s = self._analyze_text(text)
            scores.append(s)

        avg_sentiment = float(np.mean(scores))
        # Convert -1..1 to 0..100 score
        score = (avg_sentiment + 1) * 50

        return {
            "score": round(score, 2),
            "sentiment": round(avg_sentiment, 4),
            "n_articles": len(articles),
            "articles": [
                {
                    "title": a["title"],
                    "sentiment": round(self._analyze_text(f"{a['title']} {a['summary']}"), 4),
                    "published": a["published"],
                }
                for a in articles[:5]  # Top 5 for breakdown
            ],
        }

    def _proxy_sentiment(self, df: pd.DataFrame) -> dict:
        """Fallback: compute sentiment from price & volume momentum."""
        df = df.copy()
        df["returns"] = df["close"].pct_change()
        df["vol_ma"] = df["volume"].rolling(20).mean()

        recent = df.iloc[-5:]
        avg_return = recent["returns"].mean()
        avg_volume = recent["volume"].mean()
        base_vol = df["volume"].tail(20).mean()
        vol_ratio = avg_volume / base_vol if base_vol > 0 else 1.0

        price_score = max(0, min(25, 12.5 + avg_return * 500))
        volume_score = min(25, vol_ratio * 12.5)
        sentiment = (price_score + volume_score - 25) / 25
        score = (sentiment + 1) * 50

        return {
            "score": round(float(score), 2),
            "sentiment": round(float(sentiment), 4),
            "n_articles": 0,
            "articles": [],
        }

    def compute(self, ticker: str) -> dict:
        """Compute sentiment score for a ticker.

        Aggregates multiple sentiment sources with weighted scoring:
        1. Foreign Net Flow (weight: 0.30) — institutional accumulation/distribution
        2. Broker Summary / Smart Money (weight: 0.25) — broker-level flow tracking
        3. Social Media (weight: 0.20) — Reddit + Twitter real-time sentiment
        4. Google Trends (weight: 0.15) — leading indicator from search interest
        5. News NLP (weight: 0.10) — Indonesian news lexicon (lagging but confirms)

        Falls back to price/volume proxy if no real-time sources available.
        """
        df = self.storage.load_ohlcv(ticker)
        if df.empty:
            return {"status": "error", "message": "No OHLCV"}

        # Import sentiment sources
        from trading_system.sentiment.foreign_flow import ForeignFlowSentiment
        from trading_system.sentiment.broker_summary import BrokerSummarySentiment
        from trading_system.sentiment.social_media import SocialMediaSentiment
        from trading_system.sentiment.google_trends import GoogleTrendsSentiment

        # Initialize sources
        sources = {
            "foreign_flow": ForeignFlowSentiment(storage=self.storage),
            "broker_summary": BrokerSummarySentiment(storage=self.storage),
            "social_media": SocialMediaSentiment(storage=self.storage),
            "google_trends": GoogleTrendsSentiment(storage=self.storage),
        }

        # Weights for each source (sum = 1.0)
        weights = {
            "foreign_flow": 0.30,
            "broker_summary": 0.25,
            "social_media": 0.20,
            "google_trends": 0.15,
            "news_nlp": 0.10,
        }

        # Collect results from each source
        results = {}
        active_weights = {}

        # Real-time sources
        for name, source in sources.items():
            result = source.compute(ticker)
            if result is not None:
                results[name] = result
                active_weights[name] = weights[name]

        # News NLP (lagging but useful as confirmation)
        news_result = self._news_sentiment(ticker)
        if news_result is not None:
            results["news_nlp"] = {
                "score": news_result["score"],
                "sentiment": news_result["sentiment"],
                "signal": "news_" + ("bullish" if news_result["sentiment"] > 0.1 else "bearish" if news_result["sentiment"] < -0.1 else "neutral"),
                "detail": {"n_articles": news_result["n_articles"]},
            }
            active_weights["news_nlp"] = weights["news_nlp"]

        # If no real-time sources available, use proxy
        if not results:
            proxy = self._proxy_sentiment(df)
            # Save proxy score to DB
            if self.storage:
                self.storage.save_score(ticker, "sentiment", proxy["score"], {
                    "source": "price_volume_proxy",
                    "sentiment": proxy["sentiment"],
                })
            return {
                "status": "ok",
                "engine": self.name,
                "score": proxy["score"],
                "sentiment": proxy["sentiment"],
                "breakdown": {
                    "source": "price_volume_proxy",
                    "n_articles": 0,
                    "articles": [],
                    "note": "No real-time sentiment sources available. Using price/volume proxy.",
                },
            }

        # Normalize weights for active sources only
        total_weight = sum(active_weights.values())
        if total_weight == 0:
            normalized_weights = {k: 1.0 / len(active_weights) for k in active_weights}
        else:
            normalized_weights = {k: v / total_weight for k, v in active_weights.items()}

        # Compute weighted aggregate
        weighted_score = sum(results[name]["score"] * normalized_weights[name] for name in results)
        weighted_sentiment = sum(results[name]["sentiment"] * normalized_weights[name] for name in results)

        # Determine overall signal
        if weighted_sentiment > 0.1:
            signal = "bullish"
        elif weighted_sentiment < -0.1:
            signal = "bearish"
        else:
            signal = "neutral"

        # Save aggregate sentiment score to DB
        if self.storage:
            self.storage.save_score(ticker, "sentiment", weighted_score, {
                "signal": signal,
                "sentiment": round(float(weighted_sentiment), 4),
                "active_sources": list(results.keys()),
                "weights": {k: round(float(v), 4) for k, v in normalized_weights.items()},
            })
            # Save each sub-source score to DB for granular tracking
            for name in results:
                sub_engine_name = f"sentiment_{name}"
                self.storage.save_score(ticker, sub_engine_name, results[name]["score"], {
                    "sentiment": results[name]["sentiment"],
                    "signal": results[name].get("signal", "neutral"),
                    "weight": round(float(normalized_weights[name]), 4),
                    "detail": results[name].get("detail", {}),
                })

        return {
            "status": "ok",
            "engine": self.name,
            "score": round(float(weighted_score), 2),
            "sentiment": round(float(weighted_sentiment), 4),
            "signal": signal,
            "breakdown": {
                "sources": {
                    name: {
                        "score": results[name]["score"],
                        "sentiment": results[name]["sentiment"],
                        "signal": results[name].get("signal", "neutral"),
                        "weight": round(float(normalized_weights[name]), 4),
                        "detail": results[name].get("detail", {}),
                    }
                    for name in results
                },
                "active_sources": list(results.keys()),
                "inactive_sources": [s for s in weights if s not in results],
            },
        }
