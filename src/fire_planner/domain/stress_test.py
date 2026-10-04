"""Scenario stress-testing calculations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .models import StringEnum, YearMonth
from .money import apply_basis_points, ensure_money_limit
from .validation import (
    MAX_PLANNING_MONTHS,
    require_basis_points,
    require_non_negative_cents,
    require_signed_cents,
)


class StressTestType(StringEnum):
    ZERO_RETURN = "zero_return"
    ASSET_DRAWDOWN = "asset_drawdown"
    NO_ACTIVE_INCOME = "no_active_income"
    BUDGET_INCREASE = "budget_increase"


@dataclass(frozen=True, slots=True)
class StressTestPoint:
    month: YearMonth
    opening_assets_cents: int
    asset_shock_cents: int
    adjusted_opening_assets_cents: int
    investment_return_cents: int
    active_income_cents: int
    living_cost_cents: int
    asset_draw_cents: int
    withdrawal_limit_cents: int
    monthly_gap_cents: int
    closing_assets_cents: int
    withdrawal_rate_exceeded: bool
    is_negative: bool

    def __post_init__(self) -> None:
        if not isinstance(self.month, YearMonth):
            raise TypeError("month must be a YearMonth")
        require_signed_cents(self.opening_assets_cents, "opening_assets_cents")
        require_non_negative_cents(self.asset_shock_cents, "asset_shock_cents")
        require_signed_cents(
            self.adjusted_opening_assets_cents,
            "adjusted_opening_assets_cents",
        )
        require_signed_cents(
            self.investment_return_cents,
            "investment_return_cents",
        )
        for field_name in (
            "active_income_cents",
            "living_cost_cents",
            "asset_draw_cents",
            "withdrawal_limit_cents",
            "monthly_gap_cents",
        ):
            require_non_negative_cents(getattr(self, field_name), field_name)
        require_signed_cents(self.closing_assets_cents, "closing_assets_cents")

        if self.adjusted_opening_assets_cents != (
            self.opening_assets_cents - self.asset_shock_cents
        ):
            raise ValueError("adjusted opening assets must include the asset shock")
        if self.asset_draw_cents != max(
            0,
            self.living_cost_cents - self.active_income_cents,
        ):
            raise ValueError("asset draw must equal living costs not covered by income")
        expected_closing = (
            self.adjusted_opening_assets_cents
            + self.investment_return_cents
            + self.active_income_cents
            - self.living_cost_cents
        )
        if self.closing_assets_cents != expected_closing:
            raise ValueError("closing assets do not match the stress cash-flow formula")
        if self.monthly_gap_cents != max(
            0,
            self.asset_draw_cents - self.withdrawal_limit_cents,
        ):
            raise ValueError("monthly gap must reflect the withdrawal limit")
        if self.is_negative is not (self.closing_assets_cents < 0):
            raise ValueError("is_negative must reflect closing_assets_cents")


@dataclass(frozen=True, slots=True)
class StressTestResult:
    test_type: StressTestType
    passed: bool
    points: tuple[StressTestPoint, ...]
    ending_assets_cents: int
    first_failure_month: YearMonth | None

    def __post_init__(self) -> None:
        if not isinstance(self.test_type, StressTestType):
            raise TypeError("test_type must be a StressTestType")
        if not self.points:
            raise ValueError("points must not be empty")
        require_signed_cents(self.ending_assets_cents, "ending_assets_cents")
        if self.ending_assets_cents != self.points[-1].closing_assets_cents:
            raise ValueError("ending assets must match the last stress-test point")
        failures = [
            point.month
            for point in self.points
            if point.is_negative or point.withdrawal_rate_exceeded
        ]
        expected_failure_month = failures[0] if failures else None
        if self.first_failure_month != expected_failure_month:
            raise ValueError("first_failure_month must match the first failed point")
        if self.passed is not (expected_failure_month is None):
            raise ValueError("passed must reflect the stress-test points")


def stress_test(
    *,
    test_type: StressTestType,
    exit_month: YearMonth,
    exit_assets_cents: int,
    annual_budget_cents: int,
    annual_active_income_cents: int,
    withdrawal_rate_bps: int,
    months: int = 24,
) -> StressTestResult:
    """Run one deterministic monthly stress test."""
    if not isinstance(test_type, StressTestType):
        raise TypeError("test_type must be a StressTestType")
    if not isinstance(exit_month, YearMonth):
        raise TypeError("exit_month must be a YearMonth")
    require_non_negative_cents(exit_assets_cents, "exit_assets_cents")
    require_non_negative_cents(annual_budget_cents, "annual_budget_cents")
    require_non_negative_cents(
        annual_active_income_cents,
        "annual_active_income_cents",
    )
    require_basis_points(withdrawal_rate_bps, "withdrawal_rate_bps")
    if isinstance(months, bool) or not isinstance(months, int):
        raise TypeError("months must be an integer")
    if not 1 <= months <= MAX_PLANNING_MONTHS:
        raise ValueError(f"months must be between 1 and {MAX_PLANNING_MONTHS}")

    stressed_annual_budget_cents = annual_budget_cents
    if test_type is StressTestType.BUDGET_INCREASE:
        stressed_annual_budget_cents = _scale_cents(
            annual_budget_cents,
            numerator=120,
            denominator=100,
        )

    points: list[StressTestPoint] = []
    opening_assets_cents = exit_assets_cents

    for offset in range(months):
        month = exit_month.add_months(offset)
        asset_shock_cents = 0
        if test_type is StressTestType.ASSET_DRAWDOWN and offset == 0:
            asset_shock_cents = apply_basis_points(opening_assets_cents, 2_000)
        adjusted_opening_assets_cents = opening_assets_cents - asset_shock_cents
        investment_return_cents = 0

        active_income_cents = _annual_amount_for_month(
            annual_active_income_cents,
            offset,
        )
        if test_type is StressTestType.NO_ACTIVE_INCOME and offset < 24:
            active_income_cents = 0
        living_cost_cents = _annual_amount_for_month(
            stressed_annual_budget_cents,
            offset,
        )
        asset_draw_cents = max(0, living_cost_cents - active_income_cents)

        capacity_assets_cents = max(0, adjusted_opening_assets_cents)
        annual_withdrawal_limit_cents = apply_basis_points(
            capacity_assets_cents,
            withdrawal_rate_bps,
        )
        withdrawal_limit_cents = _round_divide(
            annual_withdrawal_limit_cents,
            12,
        )
        monthly_gap_cents = max(0, asset_draw_cents - withdrawal_limit_cents)
        withdrawal_rate_exceeded = (
            asset_draw_cents * 12 > annual_withdrawal_limit_cents
        )
        closing_assets_cents = (
            adjusted_opening_assets_cents
            + investment_return_cents
            + active_income_cents
            - living_cost_cents
        )
        require_signed_cents(closing_assets_cents, "closing_assets_cents")

        points.append(
            StressTestPoint(
                month=month,
                opening_assets_cents=opening_assets_cents,
                asset_shock_cents=asset_shock_cents,
                adjusted_opening_assets_cents=adjusted_opening_assets_cents,
                investment_return_cents=investment_return_cents,
                active_income_cents=active_income_cents,
                living_cost_cents=living_cost_cents,
                asset_draw_cents=asset_draw_cents,
                withdrawal_limit_cents=withdrawal_limit_cents,
                monthly_gap_cents=monthly_gap_cents,
                closing_assets_cents=closing_assets_cents,
                withdrawal_rate_exceeded=withdrawal_rate_exceeded,
                is_negative=closing_assets_cents < 0,
            )
        )
        opening_assets_cents = closing_assets_cents

    first_failure_month = next(
        (
            point.month
            for point in points
            if point.is_negative or point.withdrawal_rate_exceeded
        ),
        None,
    )
    return StressTestResult(
        test_type=test_type,
        passed=first_failure_month is None,
        points=tuple(points),
        ending_assets_cents=points[-1].closing_assets_cents,
        first_failure_month=first_failure_month,
    )


def run_all_stress_tests(
    *,
    exit_month: YearMonth,
    exit_assets_cents: int,
    annual_budget_cents: int,
    annual_active_income_cents: int,
    withdrawal_rate_bps: int,
    months: int = 24,
) -> tuple[StressTestResult, ...]:
    """Run all MVP stress-test presets in stable display order."""
    return tuple(
        stress_test(
            test_type=test_type,
            exit_month=exit_month,
            exit_assets_cents=exit_assets_cents,
            annual_budget_cents=annual_budget_cents,
            annual_active_income_cents=annual_active_income_cents,
            withdrawal_rate_bps=withdrawal_rate_bps,
            months=months,
        )
        for test_type in StressTestType
    )


def _annual_amount_for_month(annual_cents: int, month_offset: int) -> int:
    base_amount, remainder = divmod(annual_cents, 12)
    return base_amount + (1 if month_offset % 12 < remainder else 0)


def _scale_cents(value: int, *, numerator: int, denominator: int) -> int:
    scaled = Decimal(value) * Decimal(numerator) / Decimal(denominator)
    rounded = int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return ensure_money_limit(rounded)


def _round_divide(value: int, divisor: int) -> int:
    quotient = Decimal(value) / Decimal(divisor)
    return int(quotient.quantize(Decimal(1), rounding=ROUND_HALF_UP))
