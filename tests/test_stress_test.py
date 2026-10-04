"""Tests for monthly scenario stress testing."""

import pytest

from fire_planner.domain.models import YearMonth
from fire_planner.domain.stress_test import (
    StressTestType,
    run_all_stress_tests,
    stress_test,
)


def run_test(
    test_type: StressTestType,
    *,
    exit_assets_cents: int = 200_000_000,
    annual_budget_cents: int = 12_000_000,
    annual_active_income_cents: int = 6_000_000,
    months: int = 24,
):
    return stress_test(
        test_type=test_type,
        exit_month=YearMonth(2027, 4),
        exit_assets_cents=exit_assets_cents,
        annual_budget_cents=annual_budget_cents,
        annual_active_income_cents=annual_active_income_cents,
        withdrawal_rate_bps=350,
        months=months,
    )


def test_zero_return_tracks_24_months_and_passes_safe_plan() -> None:
    result = run_test(StressTestType.ZERO_RETURN)

    assert len(result.points) == 24
    assert result.passed is True
    assert result.first_failure_month is None
    assert result.ending_assets_cents == 188_000_000
    assert all(point.investment_return_cents == 0 for point in result.points)


def test_annual_amounts_are_distributed_without_losing_cents() -> None:
    result = run_test(
        StressTestType.ZERO_RETURN,
        exit_assets_cents=1_000_000,
        annual_budget_cents=101,
        annual_active_income_cents=101,
        months=24,
    )

    assert sum(point.living_cost_cents for point in result.points[:12]) == 101
    assert sum(point.living_cost_cents for point in result.points[12:]) == 101
    assert sum(point.active_income_cents for point in result.points[:12]) == 101


def test_asset_drawdown_applies_twenty_percent_once() -> None:
    result = run_test(
        StressTestType.ASSET_DRAWDOWN,
        exit_assets_cents=160_000_000,
        annual_budget_cents=0,
        annual_active_income_cents=0,
        months=2,
    )

    assert result.points[0].asset_shock_cents == 32_000_000
    assert result.points[0].adjusted_opening_assets_cents == 128_000_000
    assert result.points[0].closing_assets_cents == 128_000_000
    assert result.points[1].asset_shock_cents == 0


def test_no_active_income_suppresses_income_for_first_24_months() -> None:
    result = run_test(
        StressTestType.NO_ACTIVE_INCOME,
        annual_budget_cents=0,
        annual_active_income_cents=12_000_000,
        months=25,
    )

    assert all(point.active_income_cents == 0 for point in result.points[:24])
    assert result.points[24].active_income_cents == 1_000_000


def test_budget_increase_raises_each_year_total_by_twenty_percent() -> None:
    result = run_test(
        StressTestType.BUDGET_INCREASE,
        annual_budget_cents=10_000_001,
        annual_active_income_cents=20_000_000,
    )

    assert sum(point.living_cost_cents for point in result.points[:12]) == 12_000_001
    assert sum(point.living_cost_cents for point in result.points[12:]) == 12_000_001


def test_withdrawal_limit_failure_is_reported_before_assets_run_out() -> None:
    result = run_test(
        StressTestType.ZERO_RETURN,
        exit_assets_cents=100_000_000,
        annual_budget_cents=12_000_000,
        annual_active_income_cents=0,
        months=1,
    )

    point = result.points[0]
    assert point.asset_draw_cents == 1_000_000
    assert point.withdrawal_limit_cents == 291_667
    assert point.monthly_gap_cents == 708_333
    assert point.withdrawal_rate_exceeded is True
    assert point.is_negative is False
    assert result.passed is False
    assert result.first_failure_month == YearMonth(2027, 4)


def test_negative_assets_are_preserved_and_reported() -> None:
    result = run_test(
        StressTestType.ZERO_RETURN,
        exit_assets_cents=1_000_000,
        annual_budget_cents=24_000_000,
        annual_active_income_cents=0,
        months=2,
    )

    assert result.points[0].closing_assets_cents == -1_000_000
    assert result.points[0].is_negative is True
    assert result.points[1].opening_assets_cents == -1_000_000
    assert result.ending_assets_cents == -3_000_000
    assert result.first_failure_month == YearMonth(2027, 4)


def test_income_surplus_increases_assets_without_a_draw() -> None:
    result = run_test(
        StressTestType.ZERO_RETURN,
        exit_assets_cents=1_000_000,
        annual_budget_cents=1_200_000,
        annual_active_income_cents=2_400_000,
        months=1,
    )

    point = result.points[0]
    assert point.asset_draw_cents == 0
    assert point.closing_assets_cents == 1_100_000
    assert result.passed is True


def test_run_all_stress_tests_uses_stable_enum_order() -> None:
    results = run_all_stress_tests(
        exit_month=YearMonth(2027, 4),
        exit_assets_cents=200_000_000,
        annual_budget_cents=12_000_000,
        annual_active_income_cents=6_000_000,
        withdrawal_rate_bps=350,
    )

    assert tuple(result.test_type for result in results) == tuple(StressTestType)


@pytest.mark.parametrize("months", [0, 121])
def test_stress_test_rejects_invalid_month_count(months: int) -> None:
    with pytest.raises(ValueError, match="months must be between"):
        run_test(StressTestType.ZERO_RETURN, months=months)
