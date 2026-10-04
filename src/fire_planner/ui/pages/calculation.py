"""Visible monthly forecast and semi-FIRE scenario calculation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, MutableMapping, Sequence

import streamlit as st

from fire_planner.domain.forecast import AssetPoint, forecast_assets
from fire_planner.domain.models import (
    AssetEvent,
    AssetEventType,
    Scenario,
    ScenarioResult,
    ScenarioStatus,
    YearMonth,
)
from fire_planner.domain.money import yuan_to_cents
from fire_planner.domain.scenario import evaluate_scenario, required_assets_for_budget
from fire_planner.ui.charts import build_fire_runway_chart
from fire_planner.ui.formatters import format_bps, format_cny, format_wan
from fire_planner.ui.pages.assets import get_investable_assets_cents
from fire_planner.ui.pages.living import (
    BUDGET_FIELDS,
    budget_widget_key,
    default_budget_year,
    get_annual_budget,
)


STATUS_LABELS = {
    ScenarioStatus.GREEN: "🟢 可行",
    ScenarioStatus.YELLOW: "🟡 接近可行",
    ScenarioStatus.ORANGE: "🟠 延后可行",
    ScenarioStatus.RED: "🔴 暂不可行",
}


@dataclass(frozen=True, slots=True)
class ScenarioInput:
    scenario_id: str
    label: str
    exit_month: YearMonth
    monthly_income_yuan: int
    one_time_income_rows: tuple[tuple[int, YearMonth], ...]


def render_calculation_page() -> None:
    st.title("开始测算")
    st.caption("从当前资产逐月推演到退出节点，并展示每一步公式，不隐藏计算过程。")

    st.subheader("1｜设置测算假设")
    (
        as_of_date,
        horizon_months,
        withdrawal_rate,
        annual_return_rate,
        post_fire_monthly_income_yuan,
    ) = (
        _render_forecast_inputs()
    )
    as_of_month = YearMonth.from_date(as_of_date)
    month_options = [
        as_of_month.add_months(offset) for offset in range(horizon_months + 1)
    ]

    current_assets_cents = get_investable_assets_cents(st.session_state)
    st.subheader("2｜分别录入退出方案")
    scenario_inputs = _render_scenario_inputs(
        month_options=month_options,
        horizon_months=horizon_months,
    )
    if len({item.exit_month for item in scenario_inputs}) != len(scenario_inputs):
        st.error("每个退出方案需要选择不同月份。")
        return

    scenarios = _build_scenarios(
        scenario_inputs,
        post_fire_monthly_income_yuan=post_fire_monthly_income_yuan,
    )
    points_by_scenario = {
        item.scenario_id: _forecast_scenario(
            scenario_input=item,
            initial_assets_cents=current_assets_cents,
            as_of_month=as_of_month,
            state=st.session_state,
            annual_return_bps=round(annual_return_rate * 100),
        )
        for item in scenario_inputs
    }
    results = _evaluate_scenarios(
        scenarios=scenarios,
        points_by_scenario=points_by_scenario,
        withdrawal_rate_bps=round(withdrawal_rate * 100),
        state=st.session_state,
    )

    reference_points = max(points_by_scenario.values(), key=len)
    semi_fire_targets = _target_assets_for_points(
        points=reference_points,
        annual_active_income_cents=yuan_to_cents(post_fire_monthly_income_yuan * 12),
        withdrawal_rate_bps=round(withdrawal_rate * 100),
        state=st.session_state,
    )
    full_fire_targets = _target_assets_for_points(
        points=reference_points,
        annual_active_income_cents=0,
        withdrawal_rate_bps=round(withdrawal_rate * 100),
        state=st.session_state,
    )

    st.subheader("3｜查看逐月资产增长")
    summary_columns = st.columns(4)
    summary_columns[0].metric("当前金融资产", format_wan(current_assets_cents))
    summary_columns[1].metric("预期年化收益率", f"{annual_return_rate:.2f}%")
    summary_columns[2].metric("规划提款率", format_bps(round(withdrawal_rate * 100)))
    first_scenario = scenario_inputs[0]
    summary_columns[3].metric(
        f"{first_scenario.label} 退出资产",
        format_wan(points_by_scenario[first_scenario.scenario_id][-1].closing_assets_cents),
    )

    st.code(
        "月末资产 = 月初资产 +（方案月薪 − 当年生活预算 ÷ 12）+ 一次性收入 + 资产预期回报",
        language=None,
    )
    st.plotly_chart(
        build_fire_runway_chart(
            initial_assets_cents=current_assets_cents,
            scenario_points=points_by_scenario,
            semi_fire_targets=semi_fire_targets,
            full_fire_targets=full_fire_targets,
            scenario_results=results,
        ),
        width="stretch",
        config={"displayModeBar": False},
    )
    st.caption(
        f"当前资产单独标为起点；每条曲线使用对应方案的退出前收入。资产预期回报按月计入，年化 {annual_return_rate:.2f}%。"
    )
    st.caption(
        f"未单独填写的年份沿用 {int(st.session_state.get('budget_year', default_budget_year()))} 年生活预算。"
    )

    with st.expander("展开逐月计算明细"):
        st.dataframe(
            [
                {
                    "方案": scenario.label,
                    **_forecast_row(point),
                }
                for scenario in scenario_inputs
                for point in points_by_scenario[scenario.scenario_id]
            ],
            hide_index=True,
            width="stretch",
        )

    st.subheader("4｜比较退出方案")
    if not results:
        st.warning("退出节点的生活预算必须大于 0，且退出资产不能为负数。")
        return

    scenario_labels = {
        f"scenario-{item.scenario_id}": item.label for item in scenario_inputs
    }
    result_columns = st.columns(len(results))
    for column, result in zip(result_columns, results, strict=True):
        with column:
            _render_result_card(scenario_labels[result.scenario_id], result)

    st.dataframe(
        [
            _comparison_row(scenario_labels[result.scenario_id], result)
            for result in results
        ],
        hide_index=True,
        width="stretch",
    )
    _render_tradeoff_insights(results)

    st.subheader("5｜核对计算公式")
    st.write("每个数字都来自领域计算引擎。展开任一节点，可以逐项核对。")
    for result in results:
        _render_formula_breakdown(
            scenario_labels[result.scenario_id],
            result,
            withdrawal_rate,
        )


def _render_forecast_inputs() -> tuple[date, int, float, float, int]:
    columns = st.columns(5)
    with columns[0]:
        as_of_date = st.date_input(
            "测算起点",
            value=date.today(),
            key="calculation_as_of_date",
        )
    with columns[1]:
        horizon_months = int(
            st.slider(
                "预测月数",
                min_value=12,
                max_value=120,
                value=36,
                step=6,
                key="calculation_horizon_months",
            )
        )
    with columns[2]:
        withdrawal_rate = float(
            st.number_input(
                "规划提款率（%）",
                min_value=0.01,
                max_value=100.0,
                value=3.5,
                step=0.1,
                key="calculation_withdrawal_rate",
            )
        )
    with columns[3]:
        annual_return_rate = float(
            st.number_input(
                "预期年化收益率（%）",
                min_value=0.0,
                max_value=100.0,
                value=0.0,
                step=0.1,
                key="calculation_annual_return_rate",
                help="按月计入资产预测；负资产不产生投资回报。",
            )
        )
    with columns[4]:
        post_fire_monthly_income_yuan = int(
            st.number_input(
                "半 FIRE 后月收入（元）",
                min_value=0,
                max_value=10_000_000,
                value=5_000,
                step=500,
                key="calculation_post_fire_income",
            )
        )
    return (
        as_of_date,
        horizon_months,
        withdrawal_rate,
        annual_return_rate,
        post_fire_monthly_income_yuan,
    )


def _render_scenario_inputs(
    *,
    month_options: Sequence[YearMonth],
    horizon_months: int,
) -> list[ScenarioInput]:
    inputs: list[ScenarioInput] = []
    scenario_count = max(1, int(st.session_state.get("calculation_scenario_count", 1)))
    for index in range(scenario_count):
        scenario_id = _scenario_id(index)
        label = _scenario_label(index)
        default_offset = min(6 + index * 4, horizon_months)
        with st.container(border=True):
            st.markdown(f"**{label}｜退出前收入与退出时间**")
            exit_month = _month_selectbox(
                f"{label} 退出月份",
                month_options,
                default_offset=min(default_offset, horizon_months),
                key=f"calculation_{scenario_id}_exit_month",
            )
            scenario_month_options = [
                month for month in month_options if month <= exit_month
            ]
            income_columns = st.columns(2)
            with income_columns[0]:
                monthly_income_yuan = int(
                    st.number_input(
                        f"{label} 退出前月薪（元）",
                        min_value=0,
                        max_value=100_000_000,
                        value=50_000,
                        step=1_000,
                        key=f"calculation_{scenario_id}_monthly_income",
                    )
                )
            st.caption("退出前一次性收入（可添加多条）")
            row_count_key = f"calculation_{scenario_id}_income_row_count"
            row_count = int(st.session_state.get(row_count_key, 1))
            one_time_income_rows: list[tuple[int, YearMonth]] = []
            for row_index in range(row_count):
                row_columns = st.columns(2)
                with row_columns[0]:
                    amount_yuan = int(
                        st.number_input(
                            f"{label} 一次性收入 {row_index + 1}（元）",
                            min_value=0,
                            max_value=1_000_000_000,
                            value=0,
                            step=10_000,
                            key=f"calculation_{scenario_id}_one_time_income_{row_index}",
                        )
                    )
                with row_columns[1]:
                    event_month = _month_selectbox(
                        f"{label} 收入 {row_index + 1} 发生月份",
                        scenario_month_options,
                        default_offset=min(
                            (row_index + 1) * 3,
                            len(scenario_month_options) - 1,
                        ),
                        key=f"calculation_{scenario_id}_income_month_{row_index}",
                        disabled=amount_yuan == 0,
                    )
                if amount_yuan:
                    one_time_income_rows.append((amount_yuan, event_month))
            st.button(
                f"＋ {label} 添加一次性收入",
                key=f"add_calculation_{scenario_id}_income_row",
                on_click=_add_scenario_income_row,
                args=(row_count_key,),
            )
            inputs.append(
                ScenarioInput(
                    scenario_id=scenario_id,
                    label=label,
                    exit_month=exit_month,
                    monthly_income_yuan=monthly_income_yuan,
                    one_time_income_rows=tuple(one_time_income_rows),
                )
            )
        st.divider()
    st.button(
        "＋ 添加退出方案",
        key="add_calculation_scenario",
        on_click=_add_scenario,
    )
    return inputs


def _scenario_id(index: int) -> str:
    return str(index)


def _scenario_label(index: int) -> str:
    return f"节点 {index + 1}"


def _add_scenario() -> None:
    st.session_state["calculation_scenario_count"] = (
        int(st.session_state.get("calculation_scenario_count", 1)) + 1
    )


def _add_scenario_income_row(row_count_key: str) -> None:
    st.session_state[row_count_key] = int(st.session_state.get(row_count_key, 1)) + 1


def _annual_budget_for_forecast_year(
    *,
    year: int,
    state: MutableMapping[str, Any],
):
    planning_year = int(state.get("budget_year", default_budget_year()))
    has_explicit_budget = any(
        budget_widget_key(year, field.key) in state for field in BUDGET_FIELDS
    )
    budget_year = year if year == planning_year or has_explicit_budget else planning_year
    return get_annual_budget(year=budget_year, state=state)


def _monthly_budget_cents(*, year: int, state: MutableMapping[str, Any]) -> int:
    annual_budget_cents = _annual_budget_for_forecast_year(year=year, state=state).total_cents
    return int(
        (Decimal(annual_budget_cents) / Decimal(12)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )


def _month_selectbox(
    label: str,
    options: Sequence[YearMonth],
    *,
    default_offset: int,
    key: str,
    disabled: bool = False,
) -> YearMonth:
    option_values = [str(month) for month in options]
    default_value = option_values[default_offset]
    if st.session_state.get(key) not in option_values:
        st.session_state[key] = default_value
    selected = st.selectbox(
        label,
        options=option_values,
        key=key,
        disabled=disabled,
    )
    return YearMonth.parse(selected)


def _build_events(
    *,
    income_rows: Sequence[tuple[int, YearMonth]],
) -> list[AssetEvent]:
    events: list[AssetEvent] = []
    for index, (income_yuan, income_month) in enumerate(income_rows):
        events.append(
            AssetEvent(
                id=f"calculation-income-{index}",
                plan_id="current-plan",
                event_month=income_month,
                event_type=AssetEventType.OTHER_INCOME,
                amount_cents=yuan_to_cents(income_yuan),
            )
        )
    return events


def _build_scenarios(
    scenario_inputs: Sequence[ScenarioInput],
    *,
    post_fire_monthly_income_yuan: int,
) -> list[Scenario]:
    return [
        Scenario(
            id=f"scenario-{item.scenario_id}",
            plan_id="current-plan",
            name=item.label,
            exit_month=item.exit_month,
            post_fire_monthly_income_cents=yuan_to_cents(
                post_fire_monthly_income_yuan
            ),
        )
        for item in scenario_inputs
    ]


def _forecast_scenario(
    *,
    scenario_input: ScenarioInput,
    initial_assets_cents: int,
    as_of_month: YearMonth,
    state: MutableMapping[str, Any],
    annual_return_bps: int,
) -> list[AssetPoint]:
    months = [
        as_of_month.add_months(offset)
        for offset in range(
            as_of_month.months_until(scenario_input.exit_month) + 1
        )
    ]
    monthly_saving_by_month = {
        month: yuan_to_cents(scenario_input.monthly_income_yuan)
        - _monthly_budget_cents(year=month.year, state=state)
        for month in months
    }
    return forecast_assets(
        initial_assets_cents=initial_assets_cents,
        as_of_month=as_of_month,
        end_month=scenario_input.exit_month,
        monthly_saving_cents=0,
        events=_build_events(income_rows=scenario_input.one_time_income_rows),
        monthly_saving_by_month=monthly_saving_by_month,
        annual_return_bps=annual_return_bps,
    )


def _target_assets_for_points(
    *,
    points: Sequence[AssetPoint],
    annual_active_income_cents: int,
    withdrawal_rate_bps: int,
    state: MutableMapping[str, Any],
) -> list[int]:
    return [
        required_assets_for_budget(
            annual_budget_cents=_annual_budget_for_forecast_year(
                year=point.month.year,
                state=state,
            ).total_cents,
            annual_active_income_cents=annual_active_income_cents,
            withdrawal_rate_bps=withdrawal_rate_bps,
        )
        for point in points
    ]


def _evaluate_scenarios(
    *,
    scenarios: Sequence[Scenario],
    points_by_scenario: Mapping[str, Sequence[AssetPoint]],
    withdrawal_rate_bps: int,
    state: MutableMapping[str, Any],
) -> list[ScenarioResult]:
    evaluable = [
        scenario
        for scenario in scenarios
        if _scenario_exit_point(scenario, points_by_scenario).closing_assets_cents >= 0
        and _annual_budget_for_forecast_year(
            year=scenario.exit_month.year,
            state=state,
        ).total_cents
        > 0
    ]
    preliminary = [
        evaluate_scenario(
            scenario=scenario,
            exit_assets_cents=_scenario_exit_point(
                scenario,
                points_by_scenario,
            ).closing_assets_cents,
            annual_budget_cents=_annual_budget_for_forecast_year(
                year=scenario.exit_month.year,
                state=state,
            ).total_cents,
            withdrawal_rate_bps=withdrawal_rate_bps,
        )
        for scenario in evaluable
    ]
    return [
        evaluate_scenario(
            scenario=scenario,
            exit_assets_cents=_scenario_exit_point(
                scenario,
                points_by_scenario,
            ).closing_assets_cents,
            annual_budget_cents=_annual_budget_for_forecast_year(
                year=scenario.exit_month.year,
                state=state,
            ).total_cents,
            withdrawal_rate_bps=withdrawal_rate_bps,
            candidate_results=preliminary,
        )
        for scenario in evaluable
    ]


def _scenario_exit_point(
    scenario: Scenario,
    points_by_scenario: Mapping[str, Sequence[AssetPoint]],
) -> AssetPoint:
    points = points_by_scenario.get(scenario.id.removeprefix("scenario-"))
    if not points:
        raise ValueError(f"missing forecast points for {scenario.id}")
    if points[-1].month != scenario.exit_month:
        raise ValueError(f"forecast does not end at {scenario.exit_month}")
    return points[-1]


def _forecast_row(point: AssetPoint) -> dict[str, str]:
    return {
        "月份": str(point.month),
        "月初资产": format_cny(point.opening_assets_cents),
        "+ 月薪−月支出": format_cny(point.monthly_saving_cents),
        "+ 资产预期回报": format_cny(point.investment_return_cents),
        "+ 一次性收入": format_cny(point.one_time_income_cents),
        "= 月末资产": format_cny(point.closing_assets_cents),
    }


def _render_result_card(label: str, result: ScenarioResult) -> None:
    with st.container(border=True):
        st.markdown(f"### {label}｜{result.exit_month}")
        st.markdown(f"**{STATUS_LABELS[result.status]}**")
        st.metric("退出资产", format_wan(result.exit_assets_cents))
        st.metric("年度可支配", format_wan(result.annual_available_cents))
        gap_label = "年度缺口" if result.annual_gap_cents > 0 else "年度结余"
        st.metric(gap_label, format_wan(abs(result.annual_gap_cents)))
        st.caption(f"生活覆盖率 {result.coverage_ratio:.1%}")


def _comparison_row(label: str, result: ScenarioResult) -> dict[str, str]:
    return {
        "方案": label,
        "退出时间": str(result.exit_month),
        "退出资产": format_wan(result.exit_assets_cents),
        "资产年提款": format_wan(result.annual_withdrawal_capacity_cents),
        "主动年收入": format_wan(result.annual_active_income_cents),
        "年度可支配": format_wan(result.annual_available_cents),
        "生活预算": format_wan(result.annual_budget_cents),
        "年度缺口": format_wan(result.annual_gap_cents),
        "覆盖率": f"{result.coverage_ratio:.1%}",
        "结果": STATUS_LABELS[result.status],
    }


def _render_tradeoff_insights(results: Sequence[ScenarioResult]) -> None:
    st.markdown("#### 多工作几个月换来了什么")
    ordered = sorted(results, key=lambda result: result.exit_month)
    for earlier, later in zip(ordered, ordered[1:]):
        extra_months = earlier.exit_month.months_until(later.exit_month)
        extra_assets = later.exit_assets_cents - earlier.exit_assets_cents
        extra_available = later.annual_available_cents - earlier.annual_available_cents
        st.info(
            f"从 {earlier.exit_month} 推迟到 {later.exit_month}：多工作 {extra_months} "
            f"个月，预计多积累 {format_wan(extra_assets)}，年度可支配增加 "
            f"{format_wan(extra_available)}。"
        )


def _render_formula_breakdown(
    label: str,
    result: ScenarioResult,
    withdrawal_rate: float,
) -> None:
    with st.expander(
        f"节点 {label}｜{result.exit_month} 的完整计算",
        expanded=label == "A",
    ):
        st.markdown(
            f"""
1. **退出资产**：{format_cny(result.exit_assets_cents)}
2. **资产年度提款能力**：{format_cny(result.exit_assets_cents)} × {withdrawal_rate:.2f}% = **{format_cny(result.annual_withdrawal_capacity_cents)}**
3. **半 FIRE 后主动收入**：**{format_cny(result.annual_active_income_cents)} / 年**
4. **年度可支配资金**：{format_cny(result.annual_withdrawal_capacity_cents)} + {format_cny(result.annual_active_income_cents)} = **{format_cny(result.annual_available_cents)}**
5. **年度缺口**：{format_cny(result.annual_budget_cents)} − {format_cny(result.annual_available_cents)} = **{format_cny(result.annual_gap_cents)}**
6. **生活覆盖率**：{format_cny(result.annual_available_cents)} ÷ {format_cny(result.annual_budget_cents)} = **{result.coverage_ratio:.1%}**
7. **该资产下所需最低月收入**：**{format_cny(result.required_monthly_income_cents)} / 月**
"""
        )
        if result.next_feasible_exit_month is not None:
            st.write(f"按当前参数，下一可行节点是 {result.next_feasible_exit_month}。")
