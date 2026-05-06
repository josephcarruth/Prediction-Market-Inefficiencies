import asyncio, httpx

POLY  = "https://gamma-api.polymarket.com/markets?active=true&limit=100"
KALSHI = "https://trading-api.kalshi.com/trade-api/v2/markets?limit=100"

async def fetch_all():
    async with httpx.AsyncClient() as c:
        poly  = (await c.get(POLY)).json()
        kalshi = (await c.get(KALSHI, headers={"Authorization": "Bearer YOUR_KEY"})).json()
    return poly, kalshi["markets"]

def find_mispricings(poly, kalshi, min_gap=0.03):
    results = []
    for pm in poly:
        for km in kalshi:
            if similar(pm["question"], km["title"]):  # fuzzy match
                p_prob = pm.get("outcomePrices", [0.5])[0]
                k_prob = km.get("yes_ask", 0.5)
                gap = abs(p_prob - k_prob)
                if gap >= min_gap:
                    results.append({
                        "title": pm["question"],
                        "poly": p_prob, "kalshi": k_prob,
                        "gap": gap,
                        "action": f"buy {'Poly' if p_prob < k_prob else 'Kalshi'}"
                    })
    return sorted(results, key=lambda x: -x["gap"])