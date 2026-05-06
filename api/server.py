"""
FastAPI backend — serves mispricing data and the dashboard.

Endpoints:
  GET /              — dashboard (static/index.html)
  GET /api/status    — scanner health check
  GET /api/scan      — latest scan results (filterable)
  GET /api/scan/now  — trigger an immediate scan

Run with:
  uvicorn api.server:app --reload --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.scanner import scanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    scanner.start()
    yield
    scanner.stop()


app = FastAPI(
    title="Prediction Market Arb Finder",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/status")
async def status():
    latest = scanner.latest
    return {
        "status": "running",
        "last_scan": latest.scan_time,
        "mispricing_count": len(latest.mispricings),
        "poly_markets": latest.poly_count,
        "kalshi_markets": latest.kal_count,
        "kalshi_enabled": bool(os.getenv("KALSHI_API_KEY")),
    }


@app.get("/api/scan")
async def get_scan(
    category: str = Query("all"),
    min_gap: float = Query(0.02),
    sort: str = Query("gap"),
):
    data = scanner.latest.to_dict()
    mispricings = data["mispricings"]

    if category != "all":
        mispricings = [m for m in mispricings if m["category"] == category]

    mispricings = [m for m in mispricings if m["net_gap"] >= min_gap]

    if sort == "volume":
        mispricings.sort(key=lambda m: m["poly_volume"] + m["kal_volume"], reverse=True)
    elif sort == "cat":
        mispricings.sort(key=lambda m: m["category"])
    else:
        mispricings.sort(key=lambda m: m["net_gap"], reverse=True)

    data["mispricings"] = mispricings
    data["mispricing_count"] = len(mispricings)
    return JSONResponse(data)


@app.get("/api/scan/now")
async def scan_now():
    result = await scanner.run_once()
    return JSONResponse(result.to_dict())


@app.get("/")
async def dashboard():
    return FileResponse(STATIC_DIR / "index.html")
