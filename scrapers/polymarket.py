"""
Polymarket scraper — pulls active binary markets from the Gamma API.
No API key required.
"""

import httpx
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

GAMMA_URL = "https://gamma-api.polymarket.com/markets"


@dataclass
class PolyMarket:
    id: str
    question: str
    category: str
    yes_price: float       # 0.0 – 1.0
    no_price: float
    volume_24h: float
    liquidity: float
    end_date: Optional[str]
    url: str


def _infer_category(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ["election", "president", "senate", "congress", "vote", "party", "democrat", "republican", "trump", "biden"]):
        return "politics"
    if any(w in q for w in ["nba", "nfl", "mlb", "nhl", "soccer", "championship", "world cup", "superbowl", "playoffs"]):
        return "sports"
    if any(w in q for w in ["bitcoin", "ethereum", "crypto", "btc", "eth", "token", "blockchain", "ai", "openai", "gpt"]):
        return "crypto"
    if any(w in q for w in ["fed", "gdp", "inflation", "rate", "recession", "economy", "cpi", "unemployment"]):
        return "economics"
    return "other"


def _parse_price(raw) -> float:
    """Handle price as string '0.65' or list ['0.65', '0.35']."""
    try:
        if isinstance(raw, list):
            return float(raw[0])
        return float(raw)
    except (TypeError, ValueError, IndexError):
        return 0.5


async def fetch_polymarket(limit: int = 200) -> list[PolyMarket]:
    params = {
        "active": "true",
        "closed": "false",
        "limit": limit,
        "order": "volumeNum",
        "ascending": "false",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(GAMMA_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Polymarket fetch failed: {e}")
            return []

    markets = []
    for m in data:
        # skip non-binary or missing price data
        outcomes = m.get("outcomes", [])
        if len(outcomes) != 2:
            continue

        yes_price = _parse_price(m.get("outcomePrices", [0.5]))
        no_price = round(1.0 - yes_price, 4)

        markets.append(PolyMarket(
            id=str(m.get("id", "")),
            question=m.get("question", ""),
            category=_infer_category(m.get("question", "")),
            yes_price=yes_price,
            no_price=no_price,
            volume_24h=float(m.get("volume24hr", 0) or 0),
            liquidity=float(m.get("liquidity", 0) or 0),
            end_date=m.get("endDate"),
            url=f"https://polymarket.com/event/{m.get('slug', '')}",
        ))

    logger.info(f"Polymarket: fetched {len(markets)} active binary markets")
    return markets
