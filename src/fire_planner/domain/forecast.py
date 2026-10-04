"""Monthly financial-asset forecasting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .models import AssetEvent, YearMonth
from .validation import (
    MAX_PLANNING_MONTHS,
    require_non_negative_cents,
    require_signed_cents,
)


@dataclass(frozen=True, slots=True)
class AssetPoint:
    month: YearMonth
    opening_assets_cents: int
    monthly_saving_cents: int
    one_time_income_cents: int
    one_time_expense_cents: int
    closing_assets_cents: int
    is_negative: bool

    def __post_init__(self) -> None:
        if not isinstance(self.month, YearMonth):
            raise TypeError("month must be a YearMonth")
        require_signed_cents(self.opening_assets_cents, "opening_assets_cents")
        require_signed_cents(self.monthly_saving_cents, "monthly_saving_cents")
        require_non_negative_cents(
            self.one_time_income_cents,
            "one_time_income_cents",
        )
        require_non_negative_cents(
            self.one_time_expense_cents,
            "one_time_expense_cents",
        )
        require_signed_cents(self.closing_assets_cents, "closing_assets_cents")
        expected_closing = (
            self.opening_assets_cents
            + self.monthly_saving_cents
            + self.one_time_income_cents
            - self.one_time_expense_cents
        )
        if self.closing_assets_cents != expected_closing:
            raise ValueError("closing assets do not match the monthly cash-flow formula")
        if self.is_negative is not (self.closing_assets_cents < 0):
            raise ValueError("is_negative must reflect closing_assets_cents")


def forecast_assets(
    *,
    initial_assets_cents: int,
    as_of_month: YearMonth,
    end_month: YearMonth,
    monthly_saving_cents: int,
    events: Sequence[AssetEvent],
    monthly_saving_by_month: Mapping[YearMonth, int] | None = None,
) -> list[AssetPoint]:
    """Return inclusive month-end balances, optionally with a monthly schedule."""
    require_non_negative_cents(initial_assets_cents, "initial_assets_cents")
    require_signed_cents(monthly_saving_cents, "monthly_saving_cents")
    if not isinstance(as_of_month, YearMonth) or not isinstance(end_month, YearMonth):
        raise TypeError("as_of_month and end_month must be YearMonth values")

    forecast_months = as_of_month.months_until(end_month)
    if forecast_months < 0:
        raise ValueError("end_month must not precede as_of_month")
    if forecast_months > MAX_PLANNING_MONTHS:
        raise ValueError(f"forecast must be within {MAX_PLANNING_MONTHS} months")

    events_by_month = _group_events(
        events=events,
        as_of_month=as_of_month,
        end_month=end_month,
    )
    if monthly_saving_by_month is not None:
        for month, saving in monthly_saving_by_month.items():
            if not isinstance(month, YearMonth):
                raise TypeError("monthly_saving_by_month keys must be YearMonth values")
            if month < as_of_month or month > end_month:
                raise ValueError(
                    f"monthly saving for {month} is outside the forecast range"
                )
            require_signed_cents(saving, f"monthly_saving_by_month[{month}]")
    points: list[AssetPoint] = []
    opening_assets_cents = initial_assets_cents

    for offset in range(forecast_months + 1):
        month = as_of_month.add_months(offset)
        month_events = events_by_month.get(month, ())
        month_saving_cents = (
            monthly_saving_by_month.get(month, monthly_saving_cents)
            if monthly_saving_by_month is not None
            else monthly_saving_cents
        )
        one_time_income_cents = sum(
            event.amount_cents for event in month_events if event.is_income
        )
        one_time_expense_cents = sum(
            event.amount_cents for event in month_events if not event.is_income
        )
        require_non_negative_cents(
            one_time_income_cents,
            "one_time_income_cents",
        )
        require_non_negative_cents(
            one_time_expense_cents,
            "one_time_expense_cents",
        )
        closing_assets_cents = (
            opening_assets_cents
            + month_saving_cents
            + one_time_income_cents
            - one_time_expense_cents
        )
        require_signed_cents(closing_assets_cents, "closing_assets_cents")

        points.append(
            AssetPoint(
                month=month,
                opening_assets_cents=opening_assets_cents,
                monthly_saving_cents=month_saving_cents,
                one_time_income_cents=one_time_income_cents,
                one_time_expense_cents=one_time_expense_cents,
                closing_assets_cents=closing_assets_cents,
                is_negative=closing_assets_cents < 0,
            )
        )
        opening_assets_cents = closing_assets_cents

    return points


def _group_events(
    *,
    events: Sequence[AssetEvent],
    as_of_month: YearMonth,
    end_month: YearMonth,
) -> dict[YearMonth, tuple[AssetEvent, ...]]:
    grouped_events: dict[YearMonth, list[AssetEvent]] = {}
    event_ids: set[str] = set()
    plan_ids: set[str] = set()

    for event in events:
        if not isinstance(event, AssetEvent):
            raise TypeError("events must contain only AssetEvent values")
        if event.id in event_ids:
            raise ValueError(f"duplicate asset event id: {event.id}")
        event_ids.add(event.id)
        plan_ids.add(event.plan_id)
        if event.event_month < as_of_month or event.event_month > end_month:
            raise ValueError(
                f"asset event {event.id!r} is outside the forecast range"
            )
        grouped_events.setdefault(event.event_month, []).append(event)

    if len(plan_ids) > 1:
        raise ValueError("events must belong to one plan")

    return {
        month: tuple(sorted(month_events, key=lambda event: event.id))
        for month, month_events in grouped_events.items()
    }
