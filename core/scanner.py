"""
Scanner — runs fetches on a schedule, caches results,
and exposes the latest scan state to the API layer.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from scrapers.polymarket import fetch_polymarket
from scrapers.kalshi import fetch_kalshi
from core.matcher import match_markets, Mispricing

logger = logging.getLogger(__name__)

SCAN_INTERVAL_SECONDS = 60   # how often to re-scan


@dataclass
class ScanResult:
    mispricings: list[Mispricing] = field(default_factory=list)
    poly_count: int = 0
    kal_count: int = 0
    scan_time: Optional[float] = None   # unix timestamp
    scan_duration_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "mispricings": [asdict(m) for m in self.mispricings],
            "poly_count": self.poly_count,
            "kal_count": self.kal_count,
            "scan_time": self.scan_time,
            "scan_duration_ms": self.scan_duration_ms,
            "error": self.error,
            "mispricing_count": len(self.mispricings),
            "best_gap": round(self.mispricings[0].net_gap * 100, 2) if self.mispricings else None,
        }


class Scanner:
    def __init__(self, scan_interval: int = SCAN_INTERVAL_SECONDS):
        self.scan_interval = scan_interval
        self._latest: ScanResult = ScanResult()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @property
    def latest(self) -> ScanResult:
        return self._latest

    async def run_once(self) -> ScanResult:
        t0 = time.time()
        try:
            poly, kal = await asyncio.gather(
                fetch_polymarket(),
                fetch_kalshi(),
            )
            mispricings = match_markets(poly, kal)
            result = ScanResult(
                mispricings=mispricings,
                poly_count=len(poly),
                kal_count=len(kal),
                scan_time=time.time(),
                scan_duration_ms=int((time.time() - t0) * 1000),
            )
        except Exception as e:
            logger.exception("Scan failed")
            result = ScanResult(
                scan_time=time.time(),
                error=str(e),
                scan_duration_ms=int((time.time() - t0) * 1000),
            )

        self._latest = result
        return result

    async def _loop(self):
        while self._running:
            logger.info("Starting scan...")
            result = await self.run_once()
            logger.info(
                f"Scan done in {result.scan_duration_ms}ms — "
                f"{result.poly_count} Poly, {result.kal_count} Kalshi, "
                f"{len(result.mispricings)} mispricings"
            )
            await asyncio.sleep(self.scan_interval)

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())
            logger.info(f"Scanner started — interval: {self.scan_interval}s")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Scanner stopped")


# Singleton — imported by the API
scanner = Scanner()
