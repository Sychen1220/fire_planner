"""Living-budget input page."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, MutableMapping

import streamlit as st

from fire_planner.domain.budget import AnnualBudget, calculate_annual_budget
from fire_planner.domain.models import BudgetCadence, BudgetItem
from fire_planner.domain.money import yuan_to_cents
from fire_planner.infrastructure.storage import save_form_state
from fire_planner.ui.formatters import format_cny, format_wan


@dataclass(frozen=True, slots=True)
class BudgetField:
    key: str
    label: str
    cadence: BudgetCadence
    default_yuan: int
    help_text: str


BUDGET_FIELDS = (
    BudgetField("mortgage", "房贷", BudgetCadence.MONTHLY, 1_600, "每月房贷还款"),
    BudgetField("food", "吃饭", BudgetCadence.MONTHLY, 2_000, "日常餐饮预算"),
    BudgetField("utilities", "水电", BudgetCadence.MONTHLY, 100, "水、电、燃气等"),
    BudgetField("daily", "日用品 / 个护", BudgetCadence.MONTHLY, 300, "日用品和个人护理"),
    BudgetField("medical", "保险医疗", BudgetCadence.ANNUAL, 7_000, "年度保险和医疗预算"),
    BudgetField("transport", "交通", BudgetCadence.ANNUAL, 8_000, "公共交通、打车和出行"),
    BudgetField("hobbies", "兴趣", BudgetCadence.ANNUAL, 3_000, "兴趣课程、器材和项目"),
    BudgetField("travel", "旅行", BudgetCadence.ANNUAL, 50_000, "年度旅行预算"),
    BudgetField("social", "娱乐社交", BudgetCadence.ANNUAL, 9_000, "娱乐和社交活动"),
    BudgetField("other", "其他", BudgetCadence.ANNUAL, 0, "其他想纳入生活的支出"),
)


def default_budget_year() -> int:
    return date.today().year + 1


def budget_widget_key(year: int, field_key: str) -> str:
    return f"budget_{year}_{field_key}"


def build_budget_items(
    *,
    year: int,
    state: MutableMapping[str, Any],
) -> list[BudgetItem]:
    items: list[BudgetItem] = []
    for field in BUDGET_FIELDS:
        value_yuan = state.get(
            budget_widget_key(year, field.key),
            field.default_yuan,
        )
        items.append(
            BudgetItem(
                id=f"budget-{year}-{field.key}",
                plan_id="current-plan",
                year=year,
                category=field.label,
                cadence=field.cadence,
                amount_cents=yuan_to_cents(value_yuan),
            )
        )
    return items


def get_annual_budget(
    *,
    year: int,
    state: MutableMapping[str, Any],
) -> AnnualBudget:
    return calculate_annual_budget(
        budget_items=build_budget_items(year=year, state=state),
        year=year,
    )


def render_living_page() -> None:
    st.title("我的生活")
    st.caption("把你真正想过的生活填进来。旅行、兴趣和社交都属于生活成本。")

    year = int(
        st.number_input(
            "预算年份",
            min_value=date.today().year,
            max_value=2200,
            value=default_budget_year(),
            step=1,
            key="budget_year",
        )
    )
    if st.button("复制上一年预算", disabled=year <= date.today().year):
        for field in BUDGET_FIELDS:
            previous_key = budget_widget_key(year - 1, field.key)
            current_key = budget_widget_key(year, field.key)
            st.session_state[current_key] = st.session_state.get(
                previous_key,
                field.default_yuan,
            )
        st.rerun()

    monthly_fields = [
        field for field in BUDGET_FIELDS if field.cadence is BudgetCadence.MONTHLY
    ]
    annual_fields = [
        field for field in BUDGET_FIELDS if field.cadence is BudgetCadence.ANNUAL
    ]

    st.subheader("每月支出")
    _render_budget_fields(monthly_fields, year=year, suffix="元 / 月")

    st.subheader("每年支出")
    _render_budget_fields(annual_fields, year=year, suffix="元 / 年")

    annual_budget = get_annual_budget(year=year, state=st.session_state)
    st.divider()
    metric_columns = st.columns(3)
    metric_columns[0].metric("年度真实生活预算", format_wan(annual_budget.total_cents))
    metric_columns[1].metric(
        "平均每月生活成本",
        format_cny(round(annual_budget.total_cents / 12)),
    )
    metric_columns[2].metric("预算年份", str(year))

    with st.expander("查看分类汇总", expanded=True):
        st.dataframe(
            [
                {
                    "分类": category.category,
                    "年度金额": format_cny(category.amount_cents),
                    "占比": (
                        f"{category.amount_cents / annual_budget.total_cents:.1%}"
                        if annual_budget.total_cents
                        else "0.0%"
                    ),
                }
                for category in annual_budget.categories
            ],
            hide_index=True,
            width="stretch",
        )

    if st.button("保存生活预算", type="primary", width="stretch"):
        save_form_state(st.session_state)
        st.success(f"已保存 {year} 年生活预算。")


def _render_budget_fields(
    fields: list[BudgetField],
    *,
    year: int,
    suffix: str,
) -> None:
    columns = st.columns(2)
    for index, field in enumerate(fields):
        with columns[index % 2]:
            st.number_input(
                f"{field.label}（{suffix}）",
                min_value=0,
                max_value=10_000_000,
                value=field.default_yuan,
                step=100,
                help=field.help_text,
                key=budget_widget_key(year, field.key),
            )
