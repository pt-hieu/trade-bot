"""
Real-time market price streaming via vnstock_pipeline.stream.

Runs as a background asyncio task inside the FastAPI process.
Subscribes to portfolio + alert + watchlist tickers.
Stores latest tick data in memory for SSE broadcast.
"""

import asyncio
import contextlib
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger("stream")

# ── In-memory state ───────────────────────────────────────────────────────────

# latest_prices[ticker] = {"p": price, "cp": change_pct, "v": volume, "ts": "HH:mm:ss"}
latest_prices: dict[str, dict[str, Any]] = {}
latest_index: dict[str, Any] | None = None
stream_status: dict[str, Any] = {"connected": False, "symbols": 0, "market": "closed"}

# SSE subscriber queues: {queue_id: asyncio.Queue}
_subscribers: dict[int, asyncio.Queue] = {}
_sub_counter = 0


def subscribe() -> tuple[int, asyncio.Queue]:
    """Register a new SSE subscriber. Returns (id, queue)."""
    global _sub_counter
    _sub_counter += 1
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers[_sub_counter] = q
    return _sub_counter, q


def unsubscribe(sub_id: int) -> None:
    """Remove a subscriber."""
    _subscribers.pop(sub_id, None)


def _broadcast(event: str, data: Any) -> None:
    """Push event to all subscribers (non-blocking, drops if queue full)."""
    for q in list(_subscribers.values()):
        # Drop tick when client queue is full — slow clients shouldn't block broadcast.
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait({"event": event, "data": data})


# ── Market hours ─────────────────────────────────────────────────────────────


def _market_state() -> str:
    """Return current Vietnam market state."""
    now_utc = datetime.utcnow()
    vn_hour = (now_utc.hour + 7) % 24
    vn_min = now_utc.minute
    vn_t = vn_hour * 60 + vn_min

    if vn_t < 540:
        return "pre"  # before 9:00
    if vn_t < 555:
        return "ato"  # 9:00-9:15 ATO
    if vn_t < 690:
        return "open"  # 9:15-11:30
    if vn_t < 780:
        return "lunch"  # 11:30-13:00
    if vn_t < 885:
        return "open"  # 13:00-14:45
    if vn_t < 900:
        return "atc"  # 14:45-15:00
    return "post"


def _is_trading() -> bool:
    return _market_state() in ("open", "ato")


# ── Custom processor ──────────────────────────────────────────────────────────


class WarRoomProcessor:
    """Stores latest price ticks and broadcasts to SSE subscribers."""

    async def process(self, data: dict) -> None:
        event_type = data.get("event", data.get("type", ""))

        # Stock tick events — board (HOSE equities) and stockps
        if event_type in ("board", "stockps", "stock"):
            ticker = data.get("code") or data.get("symbol") or data.get("ticker")
            price = data.get("price") or data.get("matchPrice") or data.get("lastPrice")
            change_pct = data.get("changePct") or data.get("priceChange") or data.get("change_pct")
            volume = data.get("totalVolume") or data.get("volume") or data.get("vol")

            if ticker and price is not None:
                ts = datetime.utcnow().strftime("%H:%M:%S")
                tick = {
                    "t": str(ticker),
                    "p": int(price) if price else 0,
                    "cp": float(change_pct) if change_pct else 0.0,
                    "v": int(volume) if volume else 0,
                    "ts": ts,
                }
                latest_prices[str(ticker)] = tick
                _broadcast("tick", {str(ticker): tick})

        # Index events
        elif event_type in ("index", "indexps"):
            name = data.get("code") or data.get("indexId") or data.get("name", "VNINDEX")
            value = data.get("indexValue") or data.get("value") or data.get("close")
            change_pct = data.get("change") or data.get("changePct") or data.get("change_pct")

            if value is not None:
                ts = datetime.utcnow().strftime("%H:%M:%S")
                global latest_index
                latest_index = {
                    "name": str(name),
                    "v": float(value),
                    "cp": float(change_pct) if change_pct else 0.0,
                    "ts": ts,
                }
                _broadcast("index", latest_index)


# ── Stream runner ─────────────────────────────────────────────────────────────


async def _load_symbols_from_db() -> list[str]:
    """Load tickers to subscribe to from Neon DB."""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        logger.warning("DATABASE_URL not set — using empty symbol list")
        return []

    try:
        import asyncpg

        conn = await asyncpg.connect(db_url)
        try:
            rows = await conn.fetch("""
                SELECT DISTINCT ticker FROM portfolio_holdings
                WHERE holding_type != 'Cash'
                UNION
                SELECT DISTINCT ticker FROM alerts
                WHERE status = 'active'
                UNION
                SELECT DISTINCT ticker FROM swing_watchlist
                WHERE is_active = true
            """)
            tickers = [r["ticker"] for r in rows]
            logger.info(f"Loaded {len(tickers)} stream symbols: {tickers}")
            return tickers
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Failed to load stream symbols: {e}")
        return []


async def run_stream_forever() -> None:
    """Main loop: connect WSSClient, manage sessions, reconnect on error."""
    from vnstock_pipeline.stream import WSSClient

    processor = WarRoomProcessor()

    while True:
        state = _market_state()
        stream_status["market"] = state

        if not _is_trading():
            stream_status["connected"] = False
            _broadcast("status", stream_status)
            logger.debug(f"Market {state} — stream sleeping 60s")
            await asyncio.sleep(60)
            continue

        symbols = await _load_symbols_from_db()
        if not symbols:
            logger.warning("No symbols to stream — retrying in 120s")
            await asyncio.sleep(120)
            continue

        # Add VNINDEX symbol
        index_symbols = ["VNINDEX"]

        client = WSSClient(
            enable_session_manager=True,
            market="HOSE",
            session_check_interval=60,
        )

        # Register custom processor
        client.add_processor(processor)

        # Subscribe
        client.subscribe_symbols(symbols)
        client.subscribe_symbols(index_symbols)

        stream_status["connected"] = True
        stream_status["symbols"] = len(symbols)
        stream_status["market"] = _market_state()
        _broadcast("status", stream_status)
        logger.info(f"Stream connected — {len(symbols)} symbols")

        try:
            await client.connect()
            if client.enable_session_manager and client.session_manager:
                await client.start_session_monitoring()
            else:
                await client.wait_until_disconnected()
        except Exception as e:
            logger.error(f"Stream error: {e}")
        finally:
            # Best-effort disconnect; reconnect loop handles partial cleanup state.
            with contextlib.suppress(Exception):
                await client.disconnect()
            stream_status["connected"] = False
            _broadcast("status", stream_status)
            logger.info("Stream disconnected — reconnecting in 30s")
            await asyncio.sleep(30)
