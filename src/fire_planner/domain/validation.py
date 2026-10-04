"""Domain input validation rules."""

from __future__ import annotations

MIN_YEAR = 1900
MAX_YEAR = 2200
MAX_MONEY_CENTS = 10**12
MAX_PLANNING_MONTHS = 120


def require_non_blank(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def require_non_negative_cents(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer number of cents")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    if value > MAX_MONEY_CENTS:
        raise ValueError(f"{field_name} must not exceed {MAX_MONEY_CENTS} cents")
    return value


def require_signed_cents(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer number of cents")
    if abs(value) > MAX_MONEY_CENTS:
        raise ValueError(
            f"absolute {field_name} must not exceed {MAX_MONEY_CENTS} cents"
        )
    return value


def require_optional_non_negative_cents(
    value: int | None,
    field_name: str,
) -> int | None:
    if value is None:
        return None
    return require_non_negative_cents(value, field_name)


def require_basis_points(
    value: int,
    field_name: str,
    *,
    allow_zero: bool = False,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer number of basis points")
    minimum = 0 if allow_zero else 1
    if not minimum <= value <= 10_000:
        qualifier = "between 0 and 10000" if allow_zero else "between 1 and 10000"
        raise ValueError(f"{field_name} must be {qualifier} basis points")
    return value


def require_year(value: int, field_name: str = "year") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if not MIN_YEAR <= value <= MAX_YEAR:
        raise ValueError(f"{field_name} must be between {MIN_YEAR} and {MAX_YEAR}")
    return value


def require_positive_int(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value
