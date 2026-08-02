"""Swingy MCP Server — exposes trading data to Claude Code via SSE."""

import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Add scripts/ to path for shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from contextlib import asynccontextmanager

from fastmcp import FastMCP
from fastmcp.server.auth import StaticTokenVerifier
from tools.fundamentals import register as register_fundamentals
from tools.knowledge import register as register_knowledge
from tools.market import register as register_market
from tools.portfolio import register as register_portfolio

from shared.database import Database
from shared.trading_config import init_trading_config

MCP_API_KEY = os.environ.get("MCP_API_KEY", "")

# Fail closed: an unset key stops the server rather than serving the whole trading
# database unauthenticated.
if not MCP_API_KEY:
    raise RuntimeError("MCP_API_KEY is not set — refusing to start an unauthenticated server")

auth = StaticTokenVerifier(tokens={MCP_API_KEY: {"client_id": "mcp-client", "scopes": []}})


@asynccontextmanager
async def lifespan(app):
    """Initialize DB pool on startup, close on shutdown."""
    db = Database()
    await db.connect()
    await init_trading_config()
    try:
        yield
    finally:
        await db.disconnect()


mcp = FastMCP(
    "swingy",
    instructions=(
        "Trading data for Vietnamese stocks. "
        "Tools: get_portfolio, get_trades, get_cash, get_watchlist, "
        "get_prices, get_technicals, get_market_context, get_catalysts, "
        "get_financials, compare_financials, "
        "get_company_knowledge, get_macro_affected, get_news."
    ),
    auth=auth,
    lifespan=lifespan,
)

register_portfolio(mcp)
register_market(mcp)
register_fundamentals(mcp)
register_knowledge(mcp)

if __name__ == "__main__":
    # Loopback by default; Caddy reverse-proxies to it. Override MCP_HOST only when you
    # have a firewall in front of the instance.
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8001"))
    mcp.run(transport="sse", host=host, port=port)
