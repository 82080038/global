"""Social Media Sentiment — X (Twitter) & Reddit untuk pasar Indonesia.

Scrape social media untuk deteksi sentiment real-time sebelum price action.
- Reddit: r/IndonesiaInvesting, r/saham (gratis via PRAW)
- X/Twitter: search by ticker hashtag (butuh API key)

Sentiment analysis menggunakan Indonesian lexicon + emoji detection.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta

import numpy as np

from trading_system.sentiment.engine import POSITIVE_WORDS, NEGATIVE_WORDS

logger = logging.getLogger("sentiment.social_media")


class SocialMediaSentiment:
    """Compute sentiment from social media posts (Reddit + X)."""

    name = "social_media"

    # Subreddits for Indonesian investing
    SUBREDDITS = ["IndonesiaInvesting", "saham", "IndonesiaInvestments"]

    # Twitter search keywords per ticker
    TWITTER_KEYWORDS = {
        "BBCA.JK": ["$BBCA", "BBCA", "saham BCA", "#BBCA"],
        "TLKM.JK": ["$TLKM", "TLKM", "saham Telkom", "#TLKM"],
        "ASII.JK": ["$ASII", "ASII", "saham Astra", "#ASII"],
        "UNVR.JK": ["$UNVR", "UNVR", "saham Unilever", "#UNVR"],
        "GGRM.JK": ["$GGRM", "GGRM", "saham Gudang Garam", "#GGRM"],
        "BMRI.JK": ["$BMRI", "BMRI", "saham Mandiri", "#BMRI"],
        "BBRI.JK": ["$BBRI", "BBRI", "saham BRI", "#BBRI"],
        "ICBP.JK": ["$ICBP", "ICBP", "saham Indofood", "#ICBP"],
        "ADRO.JK": ["$ADRO", "ADRO", "saham Adaro", "#ADRO"],
        "MDKA.JK": ["$MDKA", "MDKA", "saham Merdeka", "#MDKA"],
    }

    # Emoji sentiment mapping
    POSITIVE_EMOJIS = {"🚀", "📈", "🔥", "💪", "👍", "bull", "🐂", "💰", "💎", "🙌"}
    NEGATIVE_EMOJIS = {"📉", "🐻", "🔻", "👎", "💀", "😱", "🩸", "capitulation"}

    def __init__(self, storage=None):
        self.storage = storage

    def _analyze_text(self, text: str) -> float:
        """Analyze sentiment using Indonesian lexicon + emoji detection.

        Returns score from -1.0 (very negative) to 1.0 (very positive).
        """
        text_lower = text.lower()
        tokens = re.findall(r"[a-z]+", text_lower)

        pos_count = sum(1 for t in tokens if t in POSITIVE_WORDS)
        neg_count = sum(1 for t in tokens if t in NEGATIVE_WORDS)

        # Emoji sentiment
        for emoji in self.POSITIVE_EMOJIS:
            if emoji in text_lower:
                pos_count += 2  # Emoji weighted more (strong signal)
        for emoji in self.NEGATIVE_EMOJIS:
            if emoji in text_lower:
                neg_count += 2

        total = pos_count + neg_count
        if total == 0:
            return 0.0

        return (pos_count - neg_count) / total

    def _fetch_reddit(self, ticker: str, limit: int = 30) -> list[dict]:
        """Fetch recent Reddit posts mentioning the ticker."""
        try:
            import praw
        except ImportError:
            logger.debug("praw not installed, skipping Reddit")
            return []

        keywords = self.TWITTER_KEYWORDS.get(ticker, [ticker.replace(".JK", "")])

        # Requires Reddit API credentials in .env
        import os
        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        user_agent = os.getenv("REDDIT_USER_AGENT", "trading_system/1.0")

        if not client_id or not client_secret:
            logger.debug("Reddit API credentials not set, skipping")
            return []

        try:
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )

            posts = []
            for subreddit_name in self.SUBREDDITS:
                try:
                    subreddit = reddit.subreddit(subreddit_name)
                    for submission in subreddit.hot(limit=50):
                        text = f"{submission.title} {submission.selftext}".lower()
                        if any(kw.lower() in text for kw in keywords):
                            posts.append({
                                "title": submission.title,
                                "text": submission.selftext[:500],
                                "score": submission.score,
                                "created": datetime.fromtimestamp(
                                    submission.created_utc, tz=timezone.utc
                                ).isoformat(),
                                "subreddit": subreddit_name,
                            })
                            if len(posts) >= limit:
                                break
                except Exception as e:
                    logger.debug(f"Reddit subreddit {subreddit_name} error: {e}")

            return posts
        except Exception as e:
            logger.debug(f"Reddit fetch error: {e}")
            return []

    def _fetch_twitter(self, ticker: str, limit: int = 30) -> list[dict]:
        """Fetch recent X/Twitter posts mentioning the ticker.

        Uses Twitter API v2 (requires Bearer token in .env).
        """
        try:
            import tweepy
        except ImportError:
            logger.debug("tweepy not installed, skipping Twitter")
            return []

        import os
        bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
        if not bearer_token:
            logger.debug("Twitter Bearer token not set, skipping")
            return []

        keywords = self.TWITTER_KEYWORDS.get(ticker, [f"${ticker.replace('.JK', '')}"])
        query = " OR ".join(keywords) + " -is:retweet lang:id"

        try:
            client = tweepy.Client(bearer_token=bearer_token)

            # Search recent tweets (last 7 days)
            now = datetime.now(timezone.utc)
            start_time = now - timedelta(days=7)

            response = client.search_recent_tweets(
                query=query,
                max_results=min(limit, 100),
                start_time=start_time,
                tweet_fields=["created_at", "public_metrics"],
            )

            if not response.data:
                return []

            tweets = []
            for tweet in response.data:
                tweets.append({
                    "text": tweet.text,
                    "created": tweet.created_at.isoformat() if tweet.created_at else "",
                    "likes": tweet.public_metrics.get("like_count", 0) if tweet.public_metrics else 0,
                    "retweets": tweet.public_metrics.get("retweet_count", 0) if tweet.public_metrics else 0,
                })

            return tweets
        except Exception as e:
            logger.debug(f"Twitter fetch error: {e}")
            return []

    def compute(self, ticker: str) -> dict | None:
        """Compute sentiment from social media posts.

        Combines Reddit + Twitter, weighted by engagement (likes/upvotes).
        """
        reddit_posts = self._fetch_reddit(ticker)
        twitter_posts = self._fetch_twitter(ticker)

        all_posts = []

        for post in reddit_posts:
            text = f"{post['title']} {post['text']}"
            s = self._analyze_text(text)
            weight = max(1, post.get("score", 1))  # Upvote weight
            all_posts.append({"sentiment": s, "weight": weight, "source": "reddit"})

        for post in twitter_posts:
            s = self._analyze_text(post["text"])
            weight = max(1, post.get("likes", 0) + post.get("retweets", 0) + 1)
            all_posts.append({"sentiment": s, "weight": weight, "source": "twitter"})

        if not all_posts:
            return None

        # Weighted average sentiment
        total_weight = sum(p["weight"] for p in all_posts)
        if total_weight == 0:
            avg_sentiment = float(np.mean([p["sentiment"] for p in all_posts]))
        else:
            avg_sentiment = sum(p["sentiment"] * p["weight"] for p in all_posts) / total_weight

        score = (avg_sentiment + 1) * 50

        # Count by source
        reddit_count = sum(1 for p in all_posts if p["source"] == "reddit")
        twitter_count = sum(1 for p in all_posts if p["source"] == "twitter")

        # Positive vs negative post ratio
        positive_posts = sum(1 for p in all_posts if p["sentiment"] > 0)
        negative_posts = sum(1 for p in all_posts if p["sentiment"] < 0)

        signal = (
            "social_bullish" if avg_sentiment > 0.1
            else "social_bearish" if avg_sentiment < -0.1
            else "social_neutral"
        )

        return {
            "score": round(float(score), 2),
            "sentiment": round(float(avg_sentiment), 4),
            "signal": signal,
            "detail": {
                "total_posts": len(all_posts),
                "reddit_posts": reddit_count,
                "twitter_posts": twitter_count,
                "positive_posts": positive_posts,
                "negative_posts": negative_posts,
                "positive_ratio": round(float(positive_posts / len(all_posts)), 4) if all_posts else 0,
            },
        }
