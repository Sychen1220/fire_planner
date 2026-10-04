"""Tests for semi-FIRE scenario evaluation."""

from decimal import Decimal

import pytest

from fire_planner.domain.models import Scenario, ScenarioStatus, YearMonth
from fire_planner.domain.scenario import (
    calculate_post_fire_income,
    calculate_sustainable_withdrawal,
    classify_scenario,
    evaluate_scenario,
    required_assets_for_budget,
    required_monthly_income,
)


def scenario(
    *,
    scenario_id: str = "scenario-1",
    exit_month: YearMonth = YearMonth(2027, 4),
    monthly_income_cents: int = 500_000,
    annual_income_cents: int = 0,
) -> Scenario:
    return Scenario(
        id=scenario_id,
        plan_id="plan-1",
        name=str(exit_month),
        exit_month=exit_month,
        post_fire_monthly_income_cents=monthly_income_cents,
        post_fire_annual_income_cents=annual_income_cents,
    )


def test_prd_example_is_yellow_with_exact_calculation() -> None:
    result = evaluate_scenario(
        scenario=scenario(),
        exit_assets_cents=160_000_000,
        annual_budget_cents=12_000_000,
        withdrawal_rate_bps=350,
    )

    assert result.annual_withdrawal_capacity_cents == 5_600_000
    assert result.annual_active_income_cents == 6_000_000
    assert result.annual_available_cents == 11_600_000
    assert result.annual_gap_cents == 400_000
    assert result.coverage_ratio == Decimal(29) / Decimal(30)
    assert result.status is ScenarioStatus.YELLOW
    assert result.required_monthly_income_cents == 533_334


def test_green_status_includes_exact_budget_coverage() -> None:
    result = evaluate_scenario(
        scenario=scenario(),
        exit_assets_cents=171_428_572,
        annual_budget_cents=12_000_000,
        withdrawal_rate_bps=350,
    )

    assert result.annual_available_cents == 12_000_000
    assert result.annual_gap_cents == 0
    assert result.status is ScenarioStatus.GREEN


def test_yellow_status_includes_five_percent_boundary() -> None:
    assert (
        classify_scenario(
            annual_gap_cents=500,
            annual_budget_cents=10_000,
        )
        is ScenarioStatus.YELLOW
    )


def test_red_status_starts_above_five_percent_without_later_solution() -> None:
    assert (
        classify_scenario(
            annual_gap_cents=501,
            annual_budget_cents=10_000,
        )
        is ScenarioStatus.RED
    )


def test_orange_status_points_to_earliest_later_green_candidate() -> None:
    later_green = evaluate_scenario(
        scenario=scenario(
            scenario_id="later-green",
            exit_month=YearMonth(2027, 8),
        ),
        exit_assets_cents=171_428_572,
        annual_budget_cents=12_000_000,
        withdrawal_rate_bps=350,
    )
    latest_green = evaluate_scenario(
        scenario=scenario(
            scenario_id="latest-green",
            exit_month=YearMonth(2028, 4),
        ),
        exit_assets_cents=210_000_000,
        annual_budget_cents=12_000_000,
        withdrawal_rate_bps=350,
    )

    result = evaluate_scenario(
        scenario=scenario(
            scenario_id="current",
            exit_month=YearMonth(2027, 4),
            monthly_income_cents=0,
        ),
        exit_assets_cents=160_000_000,
        annual_budget_cents=12_000_000,
        withdrawal_rate_bps=350,
        candidate_results=[latest_green, later_green],
    )

    assert result.status is ScenarioStatus.ORANGE
    assert result.next_feasible_exit_month == YearMonth(2027, 8)


def test_earlier_green_candidate_does_not_make_current_scenario_orange() -> None:
    earlier_green = evaluate_scenario(
        scenario=scenario(
            scenario_id="earlier-green",
            exit_month=YearMonth(2027, 1),
        ),
        exit_assets_cents=171_428_572,
        annual_budget_cents=12_000_000,
        withdrawal_rate_bps=350,
    )

    result = evaluate_scenario(
        scenario=scenario(
            scenario_id="current",
            exit_month=YearMonth(2027, 4),
            monthly_income_cents=0,
        ),
        exit_assets_cents=100_000_000,
        annual_budget_cents=12_000_000,
        withdrawal_rate_bps=350,
        candidate_results=[earlier_green],
    )

    assert result.status is ScenarioStatus.RED
    assert result.next_feasible_exit_month is None


def test_required_assets_rounds_up_to_cover_shortfall() -> None:
    required_assets = required_assets_for_budget(
        annual_budget_cents=12_000_000,
        annual_active_income_cents=6_000_000,
        withdrawal_rate_bps=350,
    )

    assert required_assets == 171_428_572
    assert (
        calculate_sustainable_withdrawal(
            exit_assets_cents=required_assets,
            withdrawal_rate_bps=350,
        )
        == 6_000_000
    )


def test_required_assets_is_zero_when_income_covers_budget() -> None:
    assert (
        required_assets_for_budget(
            annual_budget_cents=12_000_000,
            annual_active_income_cents=12_000_000,
            withdrawal_rate_bps=350,
        )
        == 0
    )


def test_required_monthly_income_accounts_for_other_annual_income() -> None:
    required_income = required_monthly_income(
        annual_budget_cents=12_000_000,
        exit_assets_cents=160_000_000,
        withdrawal_rate_bps=350,
        annual_other_income_cents=400_000,
    )

    assert required_income == 500_000


def test_post_fire_income_combines_monthly_and_annual_income() -> None:
    assert (
        calculate_post_fire_income(
            monthly_income_cents=500_000,
            annual_income_cents=1_000_000,
        )
        == 7_000_000
    )


def test_evaluate_scenario_requires_positive_budget() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        evaluate_scenario(
            scenario=scenario(),
            exit_assets_cents=160_000_000,
            annual_budget_cents=0,
            withdrawal_rate_bps=350,
        )
