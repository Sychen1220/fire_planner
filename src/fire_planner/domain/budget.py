"""Annual living-budget calculations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .models import BudgetCadence, BudgetItem
from .money import ensure_money_limit
from .validation import require_non_negative_cents, require_year


@dataclass(frozen=True, slots=True)
class CategoryBudget:
    category: str
    amount_cents: int

    def __post_init__(self) -> None:
        require_non_negative_cents(self.amount_cents, "amount_cents")


@dataclass(frozen=True, slots=True)
class AnnualBudget:
    year: int
    total_cents: int
    categories: tuple[CategoryBudget, ...]

    def __post_init__(self) -> None:
        require_year(self.year)
        require_non_negative_cents(self.total_cents, "total_cents")
        if sum(category.amount_cents for category in self.categories) != self.total_cents:
            raise ValueError("category amounts must equal the annual budget total")

    def amount_for(self, category: str) -> int:
        for category_budget in self.categories:
            if category_budget.category == category:
                return category_budget.amount_cents
        return 0


def calculate_annual_budget(
    *,
    budget_items: Sequence[BudgetItem],
    year: int,
) -> AnnualBudget:
    """Calculate one year's total budget and category breakdown."""
    require_year(year)
    _validate_single_plan(budget_items)

    category_totals: dict[str, int] = {}
    unique_items: set[tuple[str, BudgetCadence]] = set()

    for item in budget_items:
        if not isinstance(item, BudgetItem):
            raise TypeError("budget_items must contain only BudgetItem values")
        if item.year != year:
            continue

        unique_key = (item.category, item.cadence)
        if unique_key in unique_items:
            raise ValueError(
                "duplicate budget item for "
                f"category={item.category!r}, cadence={item.cadence.value!r}, year={year}"
            )
        unique_items.add(unique_key)

        multiplier = 12 if item.cadence is BudgetCadence.MONTHLY else 1
        annual_amount = ensure_money_limit(item.amount_cents * multiplier)
        category_totals[item.category] = ensure_money_limit(
            category_totals.get(item.category, 0) + annual_amount
        )

    categories = tuple(
        CategoryBudget(category=category, amount_cents=amount_cents)
        for category, amount_cents in sorted(category_totals.items())
    )
    total_cents = ensure_money_limit(sum(item.amount_cents for item in categories))
    return AnnualBudget(year=year, total_cents=total_cents, categories=categories)


def _validate_single_plan(budget_items: Sequence[BudgetItem]) -> None:
    plan_ids: set[str] = set()
    for item in budget_items:
        if not isinstance(item, BudgetItem):
            raise TypeError("budget_items must contain only BudgetItem values")
        plan_ids.add(item.plan_id)
    if len(plan_ids) > 1:
        raise ValueError("budget_items must belong to one plan")
