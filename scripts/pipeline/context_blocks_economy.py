"""VN economy context block formatter for agent prompt injection.

Formats VN macro snapshot (CPI, credit, GDP, FDI) as compact text block.
Token budget: ≤100 tokens.
"""


def format_vn_economy_block(vn_economy: dict | None = None) -> str:
    """Compact VN economy snapshot. Budget: ≤100 tokens.

    Args:
        vn_economy: Dict from /macro/vn-snapshot with CPI, credit, GDP, FDI data.
    """
    if not vn_economy:
        return ""

    lines = ["## VN ECONOMY"]
    parts: list[str] = []

    # CPI line
    cpi_mom = vn_economy.get("cpi_mom_pct")
    cpi_yoy = vn_economy.get("cpi_yoy_pct")
    cpi_as_of = vn_economy.get("cpi_as_of") or ""
    if cpi_mom is not None or cpi_yoy is not None:
        cpi_fragments = []
        if cpi_mom is not None:
            cpi_fragments.append(f"{cpi_mom:+.2f}% MoM")
        if cpi_yoy is not None:
            cpi_fragments.append(f"{cpi_yoy:+.1f}% YoY")
        cpi_str = f"CPI: {', '.join(cpi_fragments)}"
        if cpi_as_of:
            cpi_str += f" ({cpi_as_of})"
        parts.append(cpi_str)

    # Credit line
    credit_value = vn_economy.get("credit_trillion_vnd")
    credit_as_of = vn_economy.get("credit_as_of") or ""
    if credit_value is not None:
        credit_str = f"Credit: {credit_value:,.0f}T VND"
        if credit_as_of:
            credit_str += f" ({credit_as_of})"
        parts.append(credit_str)

    if parts:
        lines.append(" | ".join(parts))

    # GDP + FDI line
    gdp_parts: list[str] = []
    gdp_growth = vn_economy.get("gdp_growth_pct")
    gdp_quarter = vn_economy.get("gdp_quarter") or ""
    if gdp_growth is not None:
        gdp_str = (
            f"GDP {gdp_quarter}: {gdp_growth:+.1f}%" if gdp_quarter else f"GDP: {gdp_growth:+.1f}%"
        )
        gdp_parts.append(gdp_str)

    fdi_disbursed = vn_economy.get("fdi_disbursed_billion_usd")
    fdi_as_of = vn_economy.get("fdi_as_of") or ""
    if fdi_disbursed is not None:
        fdi_str = f"FDI disbursed: ${fdi_disbursed:.1f}B"
        if fdi_as_of:
            fdi_str += f" ({fdi_as_of})"
        gdp_parts.append(fdi_str)

    if gdp_parts:
        lines.append(" | ".join(gdp_parts))

    return "\n".join(lines) if len(lines) > 1 else ""
