"""Presentation-specific value formatting."""

from decimal import Decimal


def format_cny(cents: int) -> str:
    yuan = Decimal(cents) / Decimal(100)
    if cents % 100 == 0:
        return f"¥{yuan:,.0f}"
    return f"¥{yuan:,.2f}"


def format_wan(cents: int) -> str:
    wan = Decimal(cents) / Decimal(1_000_000)
    return f"{wan:,.2f} 万"


def format_bps(basis_points: int) -> str:
    return f"{Decimal(basis_points) / Decimal(100):.2f}%"
