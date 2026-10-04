"""Tests for shared domain validation rules."""

import pytest

from fire_planner.domain.validation import (
    MAX_MONEY_CENTS,
    require_basis_points,
    require_non_negative_cents,
    require_year,
)


def test_money_limit_is_inclusive() -> None:
    assert require_non_negative_cents(MAX_MONEY_CENTS, "amount") == MAX_MONEY_CENTS


@pytest.mark.parametrize("value", [-1, MAX_MONEY_CENTS + 1])
def test_money_validation_rejects_out_of_range_values(value: int) -> None:
    with pytest.raises(ValueError):
        require_non_negative_cents(value, "amount")


@pytest.mark.parametrize("value", [0, 10_001])
def test_withdrawal_rate_rejects_out_of_range_values(value: int) -> None:
    with pytest.raises(ValueError):
        require_basis_points(value, "withdrawal_rate_bps")


@pytest.mark.parametrize("value", [1899, 2201])
def test_year_rejects_out_of_range_values(value: int) -> None:
    with pytest.raises(ValueError):
        require_year(value)
