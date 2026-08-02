"""Vnstock Premium API Server."""

import asyncio
import hmac
import json
import logging
import os
from datetime import datetime

import stream as stream_module
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from routes_financials import register_financials_routes
from routes_financials_analysis import register_financials_analysis_routes
from routes_macro import register_macro_routes
from routes_market import register_market_routes
from routes_quote import register_quote_routes
from routes_technicals import register_technicals_routes
from routes_trading import register_trading_routes

logger = logging.getLogger("main")

app = FastAPI(title="Vnstock API", version="1.0.0")
API_KEY = os.environ.get("VNSTOCK_API_KEY", "")

# This service re-serves data obtained through the `vnstock` library, whose licence is
# personal-use-only and forbids redistribution. Keep it private to your own clients:
# set VNSTOCK_API_KEY, and list your own origins in VNSTOCK_ALLOWED_ORIGINS.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("VNSTOCK_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def verify_api_key(x_api_key: str = Header(None)):
    """Reject the request unless the caller presents the configured API key.

    Fails closed: an unset VNSTOCK_API_KEY locks the service rather than opening it.
    """
    if not API_KEY:
        raise HTTPException(status_code=503, detail="VNSTOCK_API_KEY is not configured")
    if not hmac.compare_digest(x_api_key or "", API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


register_macro_routes(app, verify_api_key)
register_market_routes(app, verify_api_key)
register_financials_routes(app, verify_api_key)
register_financials_analysis_routes(app, verify_api_key)
register_trading_routes(app, verify_api_key)
register_quote_routes(app, verify_api_key)
register_technicals_routes(app, verify_api_key)


@app.on_event("startup")
async def startup_event():
    """Launch market stream as background task."""
    asyncio.create_task(stream_module.run_stream_forever())
    logger.info("Market stream background task started")


@app.get("/stream/prices")
async def stream_prices(symbols: str = Query("", description="Comma-separated tickers to filter")):
    """
    SSE endpoint for real-time price updates.
    Sends initial snapshot, then streams tick/index/status events.
    Client reconnects automatically (EventSource spec).

    Deliberately unauthenticated: browsers open this with `EventSource`, which cannot
    send an `X-API-Key` header, and a key shipped to the browser is not a secret anyway.
    This endpoint therefore re-serves market data to anyone who can reach it — front it
    with your own proxy, or restrict it at the network layer, before exposing it.
    """
    filter_set: set[str] | None = None
    if symbols:
        filter_set = {s.strip().upper() for s in symbols.split(",") if s.strip()}

    async def event_generator():
        # Send initial snapshot
        snap = stream_module.latest_prices
        if filter_set:
            snap = {t: v for t, v in snap.items() if t in filter_set}
        if snap:
            yield f"event: tick\ndata: {json.dumps(snap)}\n\n"
        if stream_module.latest_index:
            yield f"event: index\ndata: {json.dumps(stream_module.latest_index)}\n\n"

        # Send current status
        yield f"event: status\ndata: {json.dumps(stream_module.stream_status)}\n\n"

        # Subscribe to live updates
        sub_id, queue = stream_module.subscribe()
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=20.0)
                    event = msg["event"]
                    data = msg["data"]

                    # Filter tick events by requested symbols
                    if event == "tick" and filter_set:
                        data = {t: v for t, v in data.items() if t in filter_set}
                        if not data:
                            continue

                    yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
                except TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            stream_module.unsubscribe(sub_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx/Caddy buffering
        },
    )


@app.get("/stream/status", dependencies=[Depends(verify_api_key)])
def stream_status_endpoint():
    """Return current stream status and subscribed symbol count."""
    return {
        **stream_module.stream_status,
        "latest_count": len(stream_module.latest_prices),
        "tickers": list(stream_module.latest_prices.keys()),
    }


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/news/articles")
def news_articles_endpoint(
    sites: str = "cafebiz,vietstock,vnexpress,vneconomy,baodautu",
    limit: int = Query(20, le=50),
    x_api_key: str = Header(None),
):
    """Fetch latest articles from Vietnamese news RSS feeds."""
    from news import news_articles

    return news_articles(sites, limit, x_api_key, verify_api_key_fn=verify_api_key)
