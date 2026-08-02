#!/usr/bin/env python3
"""Fetch messages from Telegram bot via getUpdates.

Usage:
    TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... uv run python scripts/adhoc/fetch_telegram_messages.py
    uv run python scripts/adhoc/fetch_telegram_messages.py --limit 20 --chat-id 123456789
    uv run python scripts/adhoc/fetch_telegram_messages.py --raw  # dump raw JSON

Notes:
- getUpdates only returns messages SENT TO the bot (not broadcasts the bot sent).
- Updates older than 24 hours are dropped by Telegram.
- If a webhook is set, getUpdates returns 409; delete with deleteWebhook first.
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime

import requests

API_BASE = "https://api.telegram.org/bot{token}/{method}"


def call(token: str, method: str, **params) -> dict:
    url = API_BASE.format(token=token, method=method)
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"{method} failed: {payload}")
    return payload


def format_message(update: dict) -> str:
    message = update.get("message") or update.get("edited_message") or update.get("channel_post")
    if not message:
        return f"[update_id={update.get('update_id')}] <non-message update: {list(update.keys())}>"

    chat = message.get("chat", {})
    sender = message.get("from", {})
    timestamp = datetime.fromtimestamp(message.get("date", 0), tz=UTC)
    text = message.get("text") or message.get("caption") or "<no text>"

    sender_name = sender.get("username") or sender.get("first_name") or f"id={sender.get('id')}"
    chat_label = chat.get("title") or chat.get("username") or f"id={chat.get('id')}"

    return (
        f"[{timestamp.isoformat()}] update_id={update['update_id']} "
        f"msg_id={message.get('message_id')} chat={chat_label} from={sender_name}\n  {text}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Telegram bot messages")
    parser.add_argument("--limit", type=int, default=100, help="Max updates to fetch (1-100)")
    parser.add_argument("--offset", type=int, default=None, help="Fetch updates with id >= offset")
    parser.add_argument("--chat-id", type=str, default=None, help="Filter by chat id")
    parser.add_argument(
        "--contains",
        type=str,
        default=None,
        help="Only show messages whose text/caption contains this substring (case-insensitive)",
    )
    parser.add_argument("--raw", action="store_true", help="Dump raw JSON updates")
    parser.add_argument(
        "--mark-read",
        action="store_true",
        help="Ack updates by calling getUpdates(offset=last+1). Telegram drops acked updates.",
    )
    args = parser.parse_args()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("error: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        return 2

    filter_chat = args.chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    params: dict = {"limit": args.limit, "timeout": 0}
    if args.offset is not None:
        params["offset"] = args.offset

    payload = call(token, "getUpdates", **params)
    updates = payload.get("result", [])

    if filter_chat:
        filter_chat_int = int(filter_chat)
        updates = [
            u
            for u in updates
            if (
                (u.get("message") or u.get("edited_message") or u.get("channel_post") or {})
                .get("chat", {})
                .get("id")
                == filter_chat_int
            )
        ]

    if args.contains:
        needle = args.contains.lower()
        updates = [
            u
            for u in updates
            if needle
            in (
                (
                    (
                        u.get("message") or u.get("edited_message") or u.get("channel_post") or {}
                    ).get("text")
                    or (
                        u.get("message") or u.get("edited_message") or u.get("channel_post") or {}
                    ).get("caption")
                    or ""
                ).lower()
            )
        ]

    if args.raw:
        print(json.dumps(updates, indent=2, ensure_ascii=False))
    else:
        if not updates:
            print("(no updates — bot has no unacked messages, or all older than 24h)")
        for update in updates:
            print(format_message(update))
            print()

    if args.mark_read and updates:
        last_id = max(u["update_id"] for u in updates)
        call(token, "getUpdates", offset=last_id + 1, limit=1, timeout=0)
        print(f"(acked updates through update_id={last_id})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
