"""Money precision and conversion utilities."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import TypeAlias

from .validation import MAX_MONEY_CENTS, require_non_negative_cents

MoneyInput: TypeAlias = Decimal | int | str

CENT = Decimal("0.01")
ONE_HUNDRED = Decimal(100)
TEN_THOUSAND = Decimal(10_000)


def yuan_to_cents(value: MoneyInput) -> int:
    """Convert a yuan value with at most two decimals to integer cents."""
    if isinstance(value, bool):
        raise TypeError("amount must be a Decimal, integer, or numeric string")

    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("amount must be a valid decimal number") from error

    if not amount.is_finite():
        raise ValueError("amount must be finite")
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if amount != amount.quantize(CENT):
        raise ValueError("amount must have at most two decimal places")

    cents = int(amount * ONE_HUNDRED)
    return require_non_negative_cents(cents, "amount")


def cents_to_yuan(cents: int) -> Decimal:
    """Convert integer cents to a two-decimal-place yuan value."""
    validated = require_non_negative_cents(cents, "cents")
    return (Decimal(validated) / ONE_HUNDRED).quantize(CENT)


def apply_basis_points(amount_cents: int, basis_points: int) -> int:
    """Apply a basis-point rate and round to the nearest cent."""
    validated = require_non_negative_cents(amount_cents, "amount_cents")
    if isinstance(basis_points, bool) or not isinstance(basis_points, int):
        raise TypeError("basis_points must be an integer")
    if not 0 <= basis_points <= 10_000:
        raise ValueError("basis_points must be between 0 and 10000")

    result = Decimal(validated) * Decimal(basis_points) / TEN_THOUSAND
    return int(result.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def ensure_money_limit(cents: int) -> int:
    """Validate a computed amount against the persisted money limit."""
    if cents > MAX_MONEY_CENTS:
        raise OverflowError(f"computed amount exceeds {MAX_MONEY_CENTS} cents")
    return cents
