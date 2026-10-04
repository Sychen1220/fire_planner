"""Core domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from .validation import (
    MAX_PLANNING_MONTHS,
    require_basis_points,
    require_non_blank,
    require_non_negative_cents,
    require_positive_int,
    require_signed_cents,
    require_year,
)


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class Currency(StringEnum):
    CNY = "CNY"


class AssetType(StringEnum):
    CASH = "cash"
    BANK_DEPOSIT = "bank_deposit"
    FUND = "fund"
    STOCK = "stock"
    OTHER_FINANCIAL = "other_financial"


class NonFinancialAssetType(StringEnum):
    PRIMARY_RESIDENCE = "primary_residence"
    OTHER_PROPERTY = "other_property"
    OTHER = "other"


class LiabilityType(StringEnum):
    MORTGAGE = "mortgage"
    OTHER = "other"


class BudgetCadence(StringEnum):
    MONTHLY = "monthly"
    ANNUAL = "annual"
    ONE_OFF = "one_off"


class AssetEventType(StringEnum):
    ANNUAL_BONUS = "annual_bonus"
    SEVERANCE = "severance"
    STOCK_VESTING = "stock_vesting"
    OTHER_INCOME = "other_income"
    EXTRA_EXPENSE = "extra_expense"


class ScenarioStatus(StringEnum):
    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"


def _require_enum(value: object, enum_type: type[Enum], field_name: str) -> None:
    if not isinstance(value, enum_type):
        raise TypeError(f"{field_name} must be a {enum_type.__name__}")


@dataclass(frozen=True, order=True, slots=True)
class YearMonth:
    year: int
    month: int

    def __post_init__(self) -> None:
        require_year(self.year)
        if isinstance(self.month, bool) or not isinstance(self.month, int):
            raise TypeError("month must be an integer")
        if not 1 <= self.month <= 12:
            raise ValueError("month must be between 1 and 12")

    @classmethod
    def from_date(cls, value: date) -> YearMonth:
        if not isinstance(value, date):
            raise TypeError("value must be a date")
        return cls(value.year, value.month)

    @classmethod
    def parse(cls, value: str) -> YearMonth:
        if not isinstance(value, str):
            raise TypeError("year-month must be a string")
        parts = value.split("-")
        if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
            raise ValueError("year-month must use YYYY-MM format")
        try:
            return cls(int(parts[0]), int(parts[1]))
        except ValueError as error:
            raise ValueError("year-month must be a valid YYYY-MM value") from error

    def add_months(self, months: int) -> YearMonth:
        if isinstance(months, bool) or not isinstance(months, int):
            raise TypeError("months must be an integer")
        month_index = self.year * 12 + self.month - 1 + months
        year, zero_based_month = divmod(month_index, 12)
        return YearMonth(year, zero_based_month + 1)

    def months_until(self, other: YearMonth) -> int:
        if not isinstance(other, YearMonth):
            raise TypeError("other must be a YearMonth")
        return (other.year - self.year) * 12 + other.month - self.month

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True, slots=True)
class Plan:
    id: str
    name: str
    as_of_date: date
    current_monthly_saving_cents: int
    planning_end_month: YearMonth
    created_at: datetime
    updated_at: datetime
    currency: Currency = Currency.CNY
    withdrawal_rate_bps: int = 350

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_non_blank(self.id, "id"))
        object.__setattr__(self, "name", require_non_blank(self.name, "name"))
        if not isinstance(self.as_of_date, date):
            raise TypeError("as_of_date must be a date")
        if not isinstance(self.planning_end_month, YearMonth):
            raise TypeError("planning_end_month must be a YearMonth")
        if not isinstance(self.created_at, datetime) or not isinstance(
            self.updated_at, datetime
        ):
            raise TypeError("created_at and updated_at must be datetime values")
        _require_enum(self.currency, Currency, "currency")
        require_non_negative_cents(
            self.current_monthly_saving_cents,
            "current_monthly_saving_cents",
        )
        require_basis_points(self.withdrawal_rate_bps, "withdrawal_rate_bps")
        start_month = YearMonth.from_date(self.as_of_date)
        planning_months = start_month.months_until(self.planning_end_month)
        if planning_months < 0:
            raise ValueError("planning_end_month must not precede as_of_date")
        if planning_months > MAX_PLANNING_MONTHS:
            raise ValueError(
                f"planning_end_month must be within {MAX_PLANNING_MONTHS} months"
            )
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")


@dataclass(frozen=True, slots=True)
class AssetHolding:
    id: str
    plan_id: str
    asset_type: AssetType
    amount_cents: int
    included_in_fire_assets: bool = True
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_non_blank(self.id, "id"))
        object.__setattr__(self, "plan_id", require_non_blank(self.plan_id, "plan_id"))
        _require_enum(self.asset_type, AssetType, "asset_type")
        require_non_negative_cents(self.amount_cents, "amount_cents")


@dataclass(frozen=True, slots=True)
class NonFinancialAsset:
    id: str
    plan_id: str
    asset_type: NonFinancialAssetType
    estimated_value_cents: int
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_non_blank(self.id, "id"))
        object.__setattr__(self, "plan_id", require_non_blank(self.plan_id, "plan_id"))
        _require_enum(self.asset_type, NonFinancialAssetType, "asset_type")
        require_non_negative_cents(self.estimated_value_cents, "estimated_value_cents")


@dataclass(frozen=True, slots=True)
class Liability:
    id: str
    plan_id: str
    liability_type: LiabilityType
    balance_cents: int
    monthly_payment_cents: int
    annual_interest_rate_bps: int | None = None
    remaining_months: int | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_non_blank(self.id, "id"))
        object.__setattr__(self, "plan_id", require_non_blank(self.plan_id, "plan_id"))
        _require_enum(self.liability_type, LiabilityType, "liability_type")
        require_non_negative_cents(self.balance_cents, "balance_cents")
        require_non_negative_cents(self.monthly_payment_cents, "monthly_payment_cents")
        if self.annual_interest_rate_bps is not None:
            require_basis_points(
                self.annual_interest_rate_bps,
                "annual_interest_rate_bps",
                allow_zero=True,
            )
        require_positive_int(self.remaining_months, "remaining_months")


@dataclass(frozen=True, slots=True)
class BudgetItem:
    id: str
    plan_id: str
    year: int
    category: str
    cadence: BudgetCadence
    amount_cents: int
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_non_blank(self.id, "id"))
        object.__setattr__(self, "plan_id", require_non_blank(self.plan_id, "plan_id"))
        object.__setattr__(
            self,
            "category",
            require_non_blank(self.category, "category"),
        )
        require_year(self.year)
        _require_enum(self.cadence, BudgetCadence, "cadence")
        require_non_negative_cents(self.amount_cents, "amount_cents")


@dataclass(frozen=True, slots=True)
class AssetEvent:
    id: str
    plan_id: str
    event_month: YearMonth
    event_type: AssetEventType
    amount_cents: int
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_non_blank(self.id, "id"))
        object.__setattr__(self, "plan_id", require_non_blank(self.plan_id, "plan_id"))
        if not isinstance(self.event_month, YearMonth):
            raise TypeError("event_month must be a YearMonth")
        _require_enum(self.event_type, AssetEventType, "event_type")
        require_non_negative_cents(self.amount_cents, "amount_cents")

    @property
    def is_income(self) -> bool:
        return self.event_type is not AssetEventType.EXTRA_EXPENSE


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    plan_id: str
    name: str
    exit_month: YearMonth
    post_fire_monthly_income_cents: int
    post_fire_annual_income_cents: int = 0
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_non_blank(self.id, "id"))
        object.__setattr__(self, "plan_id", require_non_blank(self.plan_id, "plan_id"))
        object.__setattr__(self, "name", require_non_blank(self.name, "name"))
        if not isinstance(self.exit_month, YearMonth):
            raise TypeError("exit_month must be a YearMonth")
        require_non_negative_cents(
            self.post_fire_monthly_income_cents,
            "post_fire_monthly_income_cents",
        )
        require_non_negative_cents(
            self.post_fire_annual_income_cents,
            "post_fire_annual_income_cents",
        )


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario_id: str
    exit_month: YearMonth
    exit_assets_cents: int
    annual_budget_cents: int
    annual_withdrawal_capacity_cents: int
    annual_active_income_cents: int
    annual_available_cents: int
    annual_gap_cents: int
    coverage_ratio: Decimal
    status: ScenarioStatus
    required_monthly_income_cents: int
    next_feasible_exit_month: YearMonth | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scenario_id",
            require_non_blank(self.scenario_id, "scenario_id"),
        )
        if not isinstance(self.exit_month, YearMonth):
            raise TypeError("exit_month must be a YearMonth")
        for field_name in (
            "exit_assets_cents",
            "annual_budget_cents",
            "annual_withdrawal_capacity_cents",
            "annual_active_income_cents",
            "annual_available_cents",
            "required_monthly_income_cents",
        ):
            require_non_negative_cents(getattr(self, field_name), field_name)
        require_signed_cents(self.annual_gap_cents, "annual_gap_cents")
        if not isinstance(self.coverage_ratio, Decimal):
            raise TypeError("coverage_ratio must be a Decimal")
        if not self.coverage_ratio.is_finite() or self.coverage_ratio < 0:
            raise ValueError("coverage_ratio must be finite and non-negative")
        _require_enum(self.status, ScenarioStatus, "status")
        if self.next_feasible_exit_month is not None and not isinstance(
            self.next_feasible_exit_month, YearMonth
        ):
            raise TypeError("next_feasible_exit_month must be a YearMonth or None")
