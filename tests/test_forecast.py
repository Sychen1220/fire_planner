"""Tests for monthly financial-asset forecasting."""

import pytest

from fire_planner.domain.forecast import forecast_assets
from fire_planner.domain.models import AssetEvent, AssetEventType, YearMonth
from fire_planner.domain.validation import MAX_MONEY_CENTS


def asset_event(
    *,
    event_id: str,
    month: YearMonth,
    event_type: AssetEventType,
    amount_cents: int,
    plan_id: str = "plan-1",
) -> AssetEvent:
    return AssetEvent(
        id=event_id,
        plan_id=plan_id,
        event_month=month,
        event_type=event_type,
        amount_cents=amount_cents,
    )


def test_forecast_assets_accumulates_monthly_cash_flows() -> None:
    points = forecast_assets(
        initial_assets_cents=100_000_000,
        as_of_month=YearMonth(2027, 1),
        end_month=YearMonth(2027, 3),
        monthly_saving_cents=3_000_000,
        events=[
            asset_event(
                event_id="bonus",
                month=YearMonth(2027, 1),
                event_type=AssetEventType.ANNUAL_BONUS,
                amount_cents=10_000_000,
            ),
            asset_event(
                event_id="travel",
                month=YearMonth(2027, 2),
                event_type=AssetEventType.EXTRA_EXPENSE,
                amount_cents=6_000_000,
            ),
            asset_event(
                event_id="severance",
                month=YearMonth(2027, 3),
                event_type=AssetEventType.SEVERANCE,
                amount_cents=20_000_000,
            ),
        ],
    )

    assert [point.closing_assets_cents for point in points] == [
        113_000_000,
        110_000_000,
        133_000_000,
    ]
    assert points[0].one_time_income_cents == 10_000_000
    assert points[1].one_time_expense_cents == 6_000_000
    assert points[2].one_time_income_cents == 20_000_000


def test_forecast_includes_events_in_exit_month() -> None:
    points = forecast_assets(
        initial_assets_cents=100_000,
        as_of_month=YearMonth(2027, 4),
        end_month=YearMonth(2027, 4),
        monthly_saving_cents=10_000,
        events=[
            asset_event(
                event_id="exit-bonus",
                month=YearMonth(2027, 4),
                event_type=AssetEventType.OTHER_INCOME,
                amount_cents=50_000,
            )
        ],
    )

    assert len(points) == 1
    assert points[0].closing_assets_cents == 160_000


def test_forecast_preserves_negative_balances() -> None:
    points = forecast_assets(
        initial_assets_cents=1_000,
        as_of_month=YearMonth(2027, 1),
        end_month=YearMonth(2027, 2),
        monthly_saving_cents=0,
        events=[
            asset_event(
                event_id="expense",
                month=YearMonth(2027, 1),
                event_type=AssetEventType.EXTRA_EXPENSE,
                amount_cents=2_000,
            )
        ],
    )

    assert points[0].closing_assets_cents == -1_000
    assert points[0].is_negative is True
    assert points[1].opening_assets_cents == -1_000
    assert points[1].closing_assets_cents == -1_000
    assert points[1].is_negative is True


def test_forecast_rejects_event_outside_range() -> None:
    event = asset_event(
        event_id="too-late",
        month=YearMonth(2027, 4),
        event_type=AssetEventType.OTHER_INCOME,
        amount_cents=100_000,
    )

    with pytest.raises(ValueError, match="outside the forecast range"):
        forecast_assets(
            initial_assets_cents=100_000,
            as_of_month=YearMonth(2027, 1),
            end_month=YearMonth(2027, 3),
            monthly_saving_cents=0,
            events=[event],
        )


def test_forecast_rejects_duplicate_event_ids() -> None:
    events = [
        asset_event(
            event_id="duplicate",
            month=YearMonth(2027, 1),
            event_type=AssetEventType.OTHER_INCOME,
            amount_cents=100_000,
        ),
        asset_event(
            event_id="duplicate",
            month=YearMonth(2027, 2),
            event_type=AssetEventType.EXTRA_EXPENSE,
            amount_cents=100_000,
        ),
    ]

    with pytest.raises(ValueError, match="duplicate asset event id"):
        forecast_assets(
            initial_assets_cents=100_000,
            as_of_month=YearMonth(2027, 1),
            end_month=YearMonth(2027, 2),
            monthly_saving_cents=0,
            events=events,
        )


def test_forecast_rejects_end_before_start() -> None:
    with pytest.raises(ValueError, match="must not precede"):
        forecast_assets(
            initial_assets_cents=100_000,
            as_of_month=YearMonth(2027, 2),
            end_month=YearMonth(2027, 1),
            monthly_saving_cents=0,
            events=[],
        )


def test_forecast_rejects_computed_overflow() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        forecast_assets(
            initial_assets_cents=MAX_MONEY_CENTS,
            as_of_month=YearMonth(2027, 1),
            end_month=YearMonth(2027, 1),
            monthly_saving_cents=1,
            events=[],
        )
