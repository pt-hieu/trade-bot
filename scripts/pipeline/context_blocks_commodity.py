"""Commodity context block formatter for agent prompt injection.

Formats live commodity prices as compact pipe-delimited text block.
Token budget: ≤100 tokens.
"""

COMMODITY_LABELS = {
    "gold_global": "Gold",
    "steel_hrc": "Steel HRC",
    "iron_ore": "Iron Ore",
    "oil_crude": "Oil",
    "gas_vn": "VN Fuel",
    "fertilizer_ure": "Urea",
}


def format_commodity_block(commodity_prices: dict[str, dict]) -> str:
    """Compact commodity price snapshot. Budget: ≤100 tokens."""
    if not commodity_prices:
        return ""

    lines = ["## COMMODITIES"]

    gold_data = commodity_prices.get("gold_global") or {}
    gold_change_5d = gold_data.get("change_5d_pct")
    if gold_change_5d is not None and gold_change_5d < -5:
        lines.append(f"⚠ GOLD CAPITULATION: {gold_change_5d:+.1f}% 5d — risk-off flight may follow")

    commodity_parts = []
    for commodity_key, data in commodity_prices.items():
        if not isinstance(data, dict):
            continue
        price = data.get("price")
        if price is None:
            continue
        change_5d = data.get("change_5d_pct")
        unit = data.get("unit") or ""
        label = COMMODITY_LABELS.get(commodity_key) or commodity_key

        price_str = f"{price:,.0f}" if price >= 100 else f"{price:.2f}"
        change_str = f" ({change_5d:+.1f}% 5d)" if change_5d is not None else ""
        unit_str = f" {unit}" if unit else ""
        commodity_parts.append(f"{label}: {price_str}{unit_str}{change_str}")

    if commodity_parts:
        # Pack into lines of ~3 items joined by " | "
        chunk_lines = []
        chunk: list[str] = []
        for part in commodity_parts:
            chunk.append(part)
            if len(chunk) >= 3:
                chunk_lines.append(" | ".join(chunk))
                chunk = []
        if chunk:
            chunk_lines.append(" | ".join(chunk))
        lines.extend(chunk_lines)

    return "\n".join(lines) if len(lines) > 1 else ""
