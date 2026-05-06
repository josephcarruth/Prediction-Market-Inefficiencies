"""
Kalshi scraper — pulls active binary markets from the Kalshi Trading API v2.
Requires a Kalshi API key set in your .env file as KALSHI_API_KEY.
Without a key, returns an empty list (graceful degradation).
"""

import httpx
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"


@dataclass
class KalshiMarket:
    id: str
    ticker: str
    question: str
    category: str
    yes_price: float       # 0.0 – 1.0  (converted from cents)
    no_price: float
    volume: float
    liquidity: float
    close_time: Optional[str]
    url: str


def _infer_category(title: str, category: str) -> str:
    cats = {
        "Politics": "politics",
        "Economics": "economics",
        "Financials": "economics",
        "Sports": "sports",
        "Crypto": "crypto",
        "Technology": "crypto",
    }
    for k, v in cats.items():
        if k.lower() in category.lower():
            return v
    # fallback: infer from title
    # could this be outsourced to a small LLM prompt for better accuracy? For now, simple keyword matching.
    t = title.lower()
    if any(w in t for w in ["election", "president", "senate", "vote"]):
        return "politics"
    if any(w in t for w in ["bitcoin", "ethereum", "crypto", "btc", "eth"]):
        return "crypto"
    if any(w in t for w in ["fed", "gdp", "inflation", "rate", "recession"]):
        return "economics"
    if any(w in t for w in ["nba", "nfl", "championship", "world cup"]):
        return "sports"
    return "other"


async def fetch_kalshi(limit: int = 200) -> list[KalshiMarket]:
    api_key = os.getenv("KALSHI_API_KEY", "")

    if not api_key:
        logger.warning("KALSHI_API_KEY not set — skipping Kalshi fetch. Add it to your .env file.")
        return []

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    params = {
        "limit": limit,
        "status": "open",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(f"{BASE_URL}/markets", headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Kalshi: invalid API key — check your KALSHI_API_KEY in .env")
            else:
                logger.error(f"Kalshi fetch failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Kalshi fetch failed: {e}")
            return []

    markets = []
    for m in data.get("markets", []):
        # Kalshi prices are in cents (0-100), convert to 0.0-1.0
        yes_ask = m.get("yes_ask", 50)
        yes_price = round(yes_ask / 100, 4)
        no_price = round(1.0 - yes_price, 4)

        ticker = m.get("ticker", "")
        markets.append(KalshiMarket(
            id=str(m.get("id", "")),
            ticker=ticker,
            question=m.get("title", ""),
            category=_infer_category(
                m.get("title", ""),
                m.get("category", ""),
            ),
            yes_price=yes_price,
            no_price=no_price,
            volume=float(m.get("volume", 0) or 0),
            liquidity=float(m.get("open_interest", 0) or 0),
            close_time=m.get("close_time"),
            url=f"https://kalshi.com/markets/{ticker}",
        ))

    logger.info(f"Kalshi: fetched {len(markets)} active markets")
    return markets
