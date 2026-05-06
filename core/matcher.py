"""
Market matcher — finds equivalent markets across Polymarket and Kalshi
using fuzzy string similarity, then calculates the mispricing gap.
"""

import re
import logging
from dataclasses import dataclass
from difflib import SequenceMatcher
from scrapers.polymarket import PolyMarket
from scrapers.kalshi import KalshiMarket

logger = logging.getLogger(__name__)

# Minimum similarity score (0-1) to consider two markets equivalent
SIMILARITY_THRESHOLD = 0.55

# Minimum price gap (0-1) to flag as a mispricing worth trading
MIN_GAP = 0.02

# Trading fee per side on each platform (approx)
POLY_FEE = 0.01   # ~1%
KALSHI_FEE = 0.01 # ~1%
TOTAL_FEES = POLY_FEE + KALSHI_FEE


@dataclass
class Mispricing:
    poly_id: str
    kal_id: str
    title: str                  # best shared description
    poly_question: str
    kal_question: str
    category: str
    poly_yes: float             # Polymarket YES price
    kal_yes: float              # Kalshi YES price
    gap: float                  # raw price gap (abs)
    net_gap: float              # gap after fees
    buy_platform: str           # where to buy YES
    sell_platform: str          # where to sell YES (buy NO)
    buy_price: float
    sell_price: float
    poly_volume: float
    kal_volume: float
    poly_url: str
    kal_url: str
    similarity: float


def _normalise(text: str) -> str:
    """Lowercase, strip punctuation and filler words for comparison."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    stopwords = {"will", "the", "a", "an", "by", "in", "on", "at", "to", "of",
                 "be", "is", "are", "was", "were", "have", "has", "do", "does",
                 "this", "that", "win", "wins", "before", "after", "above", "below"}
    tokens = [w for w in text.split() if w not in stopwords]
    return " ".join(tokens)


def _similarity(a: str, b: str) -> float:
    a_norm = _normalise(a)
    b_norm = _normalise(b)
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def _keyword_boost(a: str, b: str) -> float:
    """Extra score if both titles share significant proper nouns / numbers."""
    a_words = set(re.findall(r"\b[A-Z][a-z]+|\b\d{4}\b|\b\d+%", a))
    b_words = set(re.findall(r"\b[A-Z][a-z]+|\b\d{4}\b|\b\d+%", b))
    if not a_words or not b_words:
        return 0.0
    overlap = len(a_words & b_words) / max(len(a_words), len(b_words))
    return overlap * 0.2   # up to 0.2 bonus


def match_markets(
    poly_markets: list[PolyMarket],
    kal_markets: list[KalshiMarket],
    min_gap: float = MIN_GAP,
) -> list[Mispricing]:

    mispricings: list[Mispricing] = []
    matched_kal_ids: set[str] = set()

    for pm in poly_markets:
        best_score = 0.0
        best_km: KalshiMarket | None = None

        for km in kal_markets:
            if km.id in matched_kal_ids:
                continue
            score = _similarity(pm.question, km.question)
            score += _keyword_boost(pm.question, km.question)
            if score > best_score:
                best_score = score
                best_km = km

        if best_km is None or best_score < SIMILARITY_THRESHOLD:
            continue

        gap = abs(pm.yes_price - best_km.yes_price)
        net_gap = gap - TOTAL_FEES

        if net_gap < min_gap:
            continue

        buy_on_poly = pm.yes_price < best_km.yes_price
        mispricing = Mispricing(
            poly_id=pm.id,
            kal_id=best_km.id,
            title=pm.question,
            poly_question=pm.question,
            kal_question=best_km.question,
            category=pm.category,
            poly_yes=pm.yes_price,
            kal_yes=best_km.yes_price,
            gap=round(gap, 4),
            net_gap=round(net_gap, 4),
            buy_platform="Polymarket" if buy_on_poly else "Kalshi",
            sell_platform="Kalshi" if buy_on_poly else "Polymarket",
            buy_price=pm.yes_price if buy_on_poly else best_km.yes_price,
            sell_price=best_km.yes_price if buy_on_poly else pm.yes_price,
            poly_volume=pm.volume_24h,
            kal_volume=best_km.volume,
            poly_url=pm.url,
            kal_url=best_km.url,
            similarity=round(best_score, 3),
        )
        mispricings.append(mispricing)
        matched_kal_ids.add(best_km.id)

    mispricings.sort(key=lambda x: x.net_gap, reverse=True)
    logger.info(f"Matcher: found {len(mispricings)} mispricings from "
                f"{len(poly_markets)} Poly + {len(kal_markets)} Kalshi markets")
    return mispricings
