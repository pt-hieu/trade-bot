#!/usr/bin/env python3
"""Telegram Bot API helpers.

Provides unified message sending with:
- Message splitting for long content
- HTML parse mode with plain text fallback
- Error notification support
"""

import os

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LENGTH = 4096


def send_telegram(
    text: str,
    parse_mode: str | None = "HTML",
    split_on: str = "\n### ",
    disable_preview: bool = True,
) -> bool:
    """
    Send message via Telegram Bot API.

    Args:
        text: Message text to send
        parse_mode: "HTML", "Markdown", or None for plain text
        split_on: String to split long messages on (default: section headers)
        disable_preview: Disable link previews (default: True)

    Returns:
        True if successful

    Raises:
        ValueError: If TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set
        requests.exceptions.RequestException: On API errors
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID environment variable not set")

    url = TELEGRAM_API.format(token=token)

    # Split long messages
    messages = _split_message(text, split_on, MAX_MESSAGE_LENGTH)

    # Send each part
    for i, msg in enumerate(messages):
        payload = {
            "chat_id": chat_id,
            "text": msg,
            "disable_web_page_preview": disable_preview,
        }

        if parse_mode:
            payload["parse_mode"] = parse_mode

        print(f"Sending message part {i + 1}/{len(messages)}...")
        response = requests.post(url, json=payload, timeout=30)

        if not response.ok and parse_mode:
            # Retry without parse_mode if parsing fails
            print(f"{parse_mode} parse failed, retrying as plain text...")
            del payload["parse_mode"]
            response = requests.post(url, json=payload, timeout=30)

        if not response.ok:
            print(f"Telegram error: {response.text[:200]}")
        response.raise_for_status()
        print("  Sent successfully")

    return True


def send_telegram_error(message: str) -> bool:
    """
    Send error notification to Telegram.

    Args:
        message: Error message to send

    Returns:
        True if sent successfully, False otherwise
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Warning: Telegram credentials not set, cannot send error notification")
        return False

    url = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": f"[ERROR] {message}",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        print("Error notification sent to Telegram")
        return True
    except Exception as e:
        # Never print `e`: the request URL carries the bot token in its path, and
        # requests puts the full URL into the exception text.
        print(f"Failed to send Telegram notification: {type(e).__name__}")
        return False


def _split_on_delimiter(text: str, delimiter: str, max_length: int) -> list[str]:
    """Split text on a delimiter, keeping each chunk under max_length."""
    parts = text.split(delimiter)
    messages = []
    current = ""

    for i, part in enumerate(parts):
        if i > 0:
            part = delimiter + part

        if len(current) + len(part) > max_length - 100:
            if current:
                messages.append(current)
            current = part
        else:
            current += part

    if current:
        messages.append(current)

    return messages


def _split_message(text: str, split_on: str, max_length: int) -> list[str]:
    """
    Split a long message into smaller parts using cascading delimiters.

    Tries delimiters in order: split_on → "\\n### " → "\\n---\\n" → truncate.

    Args:
        text: Full message text
        split_on: Primary delimiter (e.g., "\\n## ")
        max_length: Maximum length per part

    Returns:
        List of message parts
    """
    if len(text) <= max_length:
        return [text]

    delimiters = [split_on, "\n### ", "\n---\n"]
    # Deduplicate while preserving order
    seen = set()
    unique_delimiters = []
    for d in delimiters:
        if d not in seen:
            seen.add(d)
            unique_delimiters.append(d)

    chunks = _split_on_delimiter(text, unique_delimiters[0], max_length)

    # Cascade: re-split any oversized chunks with finer delimiters
    for delimiter in unique_delimiters[1:]:
        refined = []
        for chunk in chunks:
            if len(chunk) > max_length:
                refined.extend(_split_on_delimiter(chunk, delimiter, max_length))
            else:
                refined.append(chunk)
        chunks = refined

    # Final pass: truncate anything still too long
    result = []
    for msg in chunks:
        if len(msg) > max_length:
            msg = msg[: max_length - 20] + "\n\n...(truncated)"
        result.append(msg)

    return result
