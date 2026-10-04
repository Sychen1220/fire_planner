"""Tests for core domain models."""

from datetime import date, datetime, timezone

import pytest

from fire_planner.domain.models import (
    AssetEvent,
    AssetEventType,
    BudgetCadence,
    BudgetItem,
    Plan,
    Scenario,
    YearMonth,
)


def test_year_month_parses_and_handles_year_boundaries() -> None:
    month = YearMonth.parse("2027-12")

    assert str(month.add_months(1)) == "2028-01"
    assert month.months_until(YearMonth(2028, 4)) == 4


@pytest.mark.parametrize("value", ["2027-1", "27-01", "2027-13", "invalid"])
def test_year_month_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        YearMonth.parse(value)


def test_plan_accepts_exactly_ten_years() -> None:
    now = datetime.now(timezone.utc)

    plan = Plan(
        id="plan-1",
        name="我的计划",
        as_of_date=date(2026, 10, 4),
        current_monthly_saving_cents=3_000_000,
        planning_end_month=YearMonth(2036, 10),
        created_at=now,
        updated_at=now,
    )

    assert plan.withdrawal_rate_bps == 350


def test_plan_rejects_more_than_ten_years() -> None:
    now = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="within 120 months"):
        Plan(
            id="plan-1",
            name="我的计划",
            as_of_date=date(2026, 10, 4),
            current_monthly_saving_cents=3_000_000,
            planning_end_month=YearMonth(2036, 11),
            created_at=now,
            updated_at=now,
        )


def test_budget_item_normalizes_category() -> None:
    item = BudgetItem(
        id="budget-1",
        plan_id="plan-1",
        year=2027,
        category="  旅行  ",
        cadence=BudgetCadence.ANNUAL,
        amount_cents=5_000_000,
    )

    assert item.category == "旅行"


def test_asset_event_distinguishes_income_and_expense() -> None:
    income = AssetEvent(
        id="event-1",
        plan_id="plan-1",
        event_month=YearMonth(2027, 4),
        event_type=AssetEventType.SEVERANCE,
        amount_cents=20_000_000,
    )
    expense = AssetEvent(
        id="event-2",
        plan_id="plan-1",
        event_month=YearMonth(2027, 5),
        event_type=AssetEventType.EXTRA_EXPENSE,
        amount_cents=6_000_000,
    )

    assert income.is_income is True
    assert expense.is_income is False


def test_scenario_rejects_negative_income() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        Scenario(
            id="scenario-1",
            plan_id="plan-1",
            name="2027 年 4 月",
            exit_month=YearMonth(2027, 4),
            post_fire_monthly_income_cents=-1,
        )

