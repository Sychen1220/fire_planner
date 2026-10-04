"""Semi-FIRE scenario evaluation."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from .models import Scenario, ScenarioResult, ScenarioStatus, YearMonth
from .money import apply_basis_points, ensure_money_limit
from .validation import (
    require_basis_points,
    require_non_negative_cents,
    require_signed_cents,
)


def calculate_sustainable_withdrawal(
    *,
    exit_assets_cents: int,
    withdrawal_rate_bps: int,
) -> int:
    """Calculate annual asset support at the planning withdrawal rate."""
    require_non_negative_cents(exit_assets_cents, "exit_assets_cents")
    require_basis_points(withdrawal_rate_bps, "withdrawal_rate_bps")
    return apply_basis_points(exit_assets_cents, withdrawal_rate_bps)


def calculate_post_fire_income(
    *,
    monthly_income_cents: int,
    annual_income_cents: int = 0,
) -> int:
    """Calculate total annual active income after leaving high-intensity work."""
    require_non_negative_cents(monthly_income_cents, "monthly_income_cents")
    require_non_negative_cents(annual_income_cents, "annual_income_cents")
    return ensure_money_limit(monthly_income_cents * 12 + annual_income_cents)


def calculate_fire_gap(
    *,
    annual_budget_cents: int,
    annual_available_cents: int,
) -> int:
    """Return budget minus available funds; negative means a surplus."""
    require_non_negative_cents(annual_budget_cents, "annual_budget_cents")
    require_non_negative_cents(annual_available_cents, "annual_available_cents")
    return annual_budget_cents - annual_available_cents


def required_assets_for_budget(
    *,
    annual_budget_cents: int,
    annual_active_income_cents: int,
    withdrawal_rate_bps: int,
) -> int:
    """Return the minimum assets needed to cover the remaining annual budget."""
    require_non_negative_cents(annual_budget_cents, "annual_budget_cents")
    require_non_negative_cents(
        annual_active_income_cents,
        "annual_active_income_cents",
    )
    require_basis_points(withdrawal_rate_bps, "withdrawal_rate_bps")

    annual_shortfall_cents = max(
        0,
        annual_budget_cents - annual_active_income_cents,
    )
    required_assets_cents = _ceil_divide(
        annual_shortfall_cents * 10_000,
        withdrawal_rate_bps,
    )
    return ensure_money_limit(required_assets_cents)


def required_monthly_income(
    *,
    annual_budget_cents: int,
    exit_assets_cents: int,
    withdrawal_rate_bps: int,
    annual_other_income_cents: int = 0,
) -> int:
    """Return the minimum recurring monthly income needed for the budget."""
    require_non_negative_cents(annual_budget_cents, "annual_budget_cents")
    require_non_negative_cents(exit_assets_cents, "exit_assets_cents")
    require_non_negative_cents(
        annual_other_income_cents,
        "annual_other_income_cents",
    )
    annual_withdrawal_cents = calculate_sustainable_withdrawal(
        exit_assets_cents=exit_assets_cents,
        withdrawal_rate_bps=withdrawal_rate_bps,
    )
    annual_shortfall_cents = max(
        0,
        annual_budget_cents
        - annual_withdrawal_cents
        - annual_other_income_cents,
    )
    return _ceil_divide(annual_shortfall_cents, 12)


def evaluate_scenario(
    *,
    scenario: Scenario,
    exit_assets_cents: int,
    annual_budget_cents: int,
    withdrawal_rate_bps: int,
    candidate_results: Sequence[ScenarioResult] = (),
) -> ScenarioResult:
    """Evaluate one exit scenario and return a deterministic result."""
    if not isinstance(scenario, Scenario):
        raise TypeError("scenario must be a Scenario")
    require_non_negative_cents(exit_assets_cents, "exit_assets_cents")
    require_non_negative_cents(annual_budget_cents, "annual_budget_cents")
    if annual_budget_cents == 0:
        raise ValueError("annual_budget_cents must be positive")
    require_basis_points(withdrawal_rate_bps, "withdrawal_rate_bps")
    _validate_candidate_results(candidate_results)

    annual_withdrawal_capacity_cents = calculate_sustainable_withdrawal(
        exit_assets_cents=exit_assets_cents,
        withdrawal_rate_bps=withdrawal_rate_bps,
    )
    annual_active_income_cents = calculate_post_fire_income(
        monthly_income_cents=scenario.post_fire_monthly_income_cents,
        annual_income_cents=scenario.post_fire_annual_income_cents,
    )
    annual_available_cents = ensure_money_limit(
        annual_withdrawal_capacity_cents + annual_active_income_cents
    )
    annual_gap_cents = calculate_fire_gap(
        annual_budget_cents=annual_budget_cents,
        annual_available_cents=annual_available_cents,
    )
    coverage_ratio = Decimal(annual_available_cents) / Decimal(annual_budget_cents)
    next_feasible_exit_month = _find_next_feasible_exit_month(
        current_exit_month=scenario.exit_month,
        candidate_results=candidate_results,
    )
    status = classify_scenario(
        annual_gap_cents=annual_gap_cents,
        annual_budget_cents=annual_budget_cents,
        next_feasible_exit_month=next_feasible_exit_month,
    )

    return ScenarioResult(
        scenario_id=scenario.id,
        exit_month=scenario.exit_month,
        exit_assets_cents=exit_assets_cents,
        annual_budget_cents=annual_budget_cents,
        annual_withdrawal_capacity_cents=annual_withdrawal_capacity_cents,
        annual_active_income_cents=annual_active_income_cents,
        annual_available_cents=annual_available_cents,
        annual_gap_cents=annual_gap_cents,
        coverage_ratio=coverage_ratio,
        status=status,
        required_monthly_income_cents=required_monthly_income(
            annual_budget_cents=annual_budget_cents,
            exit_assets_cents=exit_assets_cents,
            withdrawal_rate_bps=withdrawal_rate_bps,
            annual_other_income_cents=scenario.post_fire_annual_income_cents,
        ),
        next_feasible_exit_month=next_feasible_exit_month,
    )


def classify_scenario(
    *,
    annual_gap_cents: int,
    annual_budget_cents: int,
    next_feasible_exit_month: YearMonth | None = None,
) -> ScenarioStatus:
    """Classify a result using exact gap boundaries."""
    require_signed_cents(annual_gap_cents, "annual_gap_cents")
    require_non_negative_cents(annual_budget_cents, "annual_budget_cents")
    if annual_budget_cents == 0:
        raise ValueError("annual_budget_cents must be positive")
    if next_feasible_exit_month is not None and not isinstance(
        next_feasible_exit_month,
        YearMonth,
    ):
        raise TypeError("next_feasible_exit_month must be a YearMonth or None")

    if annual_gap_cents <= 0:
        return ScenarioStatus.GREEN
    if annual_gap_cents * 100 <= annual_budget_cents * 5:
        return ScenarioStatus.YELLOW
    if next_feasible_exit_month is not None:
        return ScenarioStatus.ORANGE
    return ScenarioStatus.RED


def _find_next_feasible_exit_month(
    *,
    current_exit_month: YearMonth,
    candidate_results: Sequence[ScenarioResult],
) -> YearMonth | None:
    feasible_months = [
        result.exit_month
        for result in candidate_results
        if result.exit_month > current_exit_month and result.annual_gap_cents <= 0
    ]
    return min(feasible_months, default=None)


def _validate_candidate_results(
    candidate_results: Sequence[ScenarioResult],
) -> None:
    for result in candidate_results:
        if not isinstance(result, ScenarioResult):
            raise TypeError("candidate_results must contain only ScenarioResult values")


def _ceil_divide(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    return -(-numerator // denominator)
