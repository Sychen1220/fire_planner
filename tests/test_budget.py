"""Tests for annual living-budget calculations."""

import pytest

from fire_planner.domain.budget import calculate_annual_budget
from fire_planner.domain.models import BudgetCadence, BudgetItem
from fire_planner.domain.validation import MAX_MONEY_CENTS


def budget_item(
    *,
    item_id: str,
    category: str,
    cadence: BudgetCadence,
    amount_cents: int,
    year: int = 2027,
    plan_id: str = "plan-1",
) -> BudgetItem:
    return BudgetItem(
        id=item_id,
        plan_id=plan_id,
        year=year,
        category=category,
        cadence=cadence,
        amount_cents=amount_cents,
    )


def test_calculate_annual_budget_combines_all_cadences() -> None:
    result = calculate_annual_budget(
        budget_items=[
            budget_item(
                item_id="mortgage",
                category="房贷",
                cadence=BudgetCadence.MONTHLY,
                amount_cents=160_000,
            ),
            budget_item(
                item_id="insurance",
                category="保险医疗",
                cadence=BudgetCadence.ANNUAL,
                amount_cents=700_000,
            ),
            budget_item(
                item_id="travel",
                category="旅行",
                cadence=BudgetCadence.ONE_OFF,
                amount_cents=5_000_000,
            ),
        ],
        year=2027,
    )

    assert result.total_cents == 7_620_000
    assert result.amount_for("房贷") == 1_920_000
    assert result.amount_for("保险医疗") == 700_000
    assert result.amount_for("旅行") == 5_000_000
    assert result.amount_for("不存在") == 0


def test_calculate_annual_budget_ignores_other_years() -> None:
    result = calculate_annual_budget(
        budget_items=[
            budget_item(
                item_id="travel-2027",
                category="旅行",
                cadence=BudgetCadence.ANNUAL,
                amount_cents=5_000_000,
            ),
            budget_item(
                item_id="travel-2028",
                category="旅行",
                cadence=BudgetCadence.ANNUAL,
                amount_cents=3_000_000,
                year=2028,
            ),
        ],
        year=2027,
    )

    assert result.total_cents == 5_000_000


def test_calculate_annual_budget_groups_same_category_across_cadences() -> None:
    result = calculate_annual_budget(
        budget_items=[
            budget_item(
                item_id="travel-monthly",
                category="旅行",
                cadence=BudgetCadence.MONTHLY,
                amount_cents=10_000,
            ),
            budget_item(
                item_id="travel-annual",
                category="旅行",
                cadence=BudgetCadence.ANNUAL,
                amount_cents=500_000,
            ),
        ],
        year=2027,
    )

    assert result.amount_for("旅行") == 620_000
    assert len(result.categories) == 1


def test_calculate_annual_budget_rejects_duplicate_category_and_cadence() -> None:
    items = [
        budget_item(
            item_id="travel-1",
            category="旅行",
            cadence=BudgetCadence.ANNUAL,
            amount_cents=100_000,
        ),
        budget_item(
            item_id="travel-2",
            category="旅行",
            cadence=BudgetCadence.ANNUAL,
            amount_cents=200_000,
        ),
    ]

    with pytest.raises(ValueError, match="duplicate budget item"):
        calculate_annual_budget(budget_items=items, year=2027)


def test_calculate_annual_budget_rejects_mixed_plans() -> None:
    items = [
        budget_item(
            item_id="food-1",
            category="吃饭",
            cadence=BudgetCadence.MONTHLY,
            amount_cents=200_000,
        ),
        budget_item(
            item_id="food-2",
            category="吃饭",
            cadence=BudgetCadence.MONTHLY,
            amount_cents=200_000,
            plan_id="plan-2",
        ),
    ]

    with pytest.raises(ValueError, match="one plan"):
        calculate_annual_budget(budget_items=items, year=2027)


def test_calculate_annual_budget_rejects_computed_overflow() -> None:
    item = budget_item(
        item_id="oversized",
        category="其他",
        cadence=BudgetCadence.MONTHLY,
        amount_cents=MAX_MONEY_CENTS,
    )

    with pytest.raises(OverflowError, match="computed amount"):
        calculate_annual_budget(budget_items=[item], year=2027)


def test_calculate_empty_annual_budget() -> None:
    result = calculate_annual_budget(budget_items=[], year=2027)

    assert result.total_cents == 0
    assert result.categories == ()
