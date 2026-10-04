"""Tests for money precision and conversion utilities."""

from decimal import Decimal

import pytest

from fire_planner.domain.money import apply_basis_points, cents_to_yuan, yuan_to_cents


@pytest.mark.parametrize(
    ("yuan", "expected_cents"),
    [
        ("0", 0),
        ("0.01", 1),
        ("1250000.50", 125_000_050),
        (Decimal("12.30"), 1_230),
    ],
)
def test_yuan_to_cents_is_exact(yuan: str | Decimal, expected_cents: int) -> None:
    assert yuan_to_cents(yuan) == expected_cents


def test_yuan_to_cents_rejects_fractional_cents() -> None:
    with pytest.raises(ValueError, match="two decimal places"):
        yuan_to_cents("1.001")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1"])
def test_yuan_to_cents_rejects_invalid_amounts(value: str) -> None:
    with pytest.raises(ValueError):
        yuan_to_cents(value)


def test_cents_to_yuan_preserves_two_decimal_places() -> None:
    assert cents_to_yuan(1_230) == Decimal("12.30")


def test_apply_basis_points_uses_half_up_rounding() -> None:
    assert apply_basis_points(100_000_000, 350) == 3_500_000
    assert apply_basis_points(150, 100) == 2

