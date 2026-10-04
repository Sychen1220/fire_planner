"""Visible monthly forecast and semi-FIRE scenario calculation."""

from __future__ import annotations

from datetime import date
from typing import Any, MutableMapping, Sequence

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
from fire_planner.ui.pages.living import get_annual_budget


STATUS_LABELS = {
    ScenarioStatus.GREEN: "🟢 可行",
    ScenarioStatus.YELLOW: "🟡 接近可行",
    ScenarioStatus.ORANGE: "🟠 延后可行",
    ScenarioStatus.RED: "🔴 暂不可行",
}


def render_calculation_page() -> None:
    st.title("开始测算")
    st.caption("从当前资产逐月推演到退出节点，并展示每一步公式，不隐藏计算过程。")

    st.subheader("1｜设置测算假设")
    as_of_date, horizon_months, monthly_saving_yuan, withdrawal_rate = (
        _render_forecast_inputs()
    )
    as_of_month = YearMonth.from_date(as_of_date)
    end_month = as_of_month.add_months(horizon_months)
    month_options = [
        as_of_month.add_months(offset) for offset in range(horizon_months + 1)
    ]

    event_columns = st.columns(2)
    with event_columns[0]:
        one_time_income_yuan = int(
            st.number_input(
                "一次性收入（元）",
                min_value=0,
                max_value=1_000_000_000,
                value=0,
                step=10_000,
                help="例如年终奖、赔偿或股票兑现。",
                key="calculation_one_time_income",
            )
        )
        income_month = _month_selectbox(
            "收入发生月份",
            month_options,
            default_offset=min(2, horizon_months),
            key="calculation_income_month",
            disabled=one_time_income_yuan == 0,
        )
    with event_columns[1]:
        one_time_expense_yuan = int(
            st.number_input(
                "一次性额外支出（元）",
                min_value=0,
                max_value=1_000_000_000,
                value=0,
                step=10_000,
                help="例如搬家、旅行或大额消费。",
                key="calculation_one_time_expense",
            )
        )
        expense_month = _month_selectbox(
            "支出发生月份",
            month_options,
            default_offset=min(4, horizon_months),
            key="calculation_expense_month",
            disabled=one_time_expense_yuan == 0,
        )

    current_assets_cents = get_investable_assets_cents(st.session_state)
    events = _build_events(
        income_yuan=one_time_income_yuan,
        income_month=income_month,
        expense_yuan=one_time_expense_yuan,
        expense_month=expense_month,
    )
    points = forecast_assets(
        initial_assets_cents=current_assets_cents,
        as_of_month=as_of_month,
        end_month=end_month,
        monthly_saving_cents=yuan_to_cents(monthly_saving_yuan),
        events=events,
    )

    st.subheader("2｜选择三个退出节点")
    post_fire_monthly_income_yuan = int(
        st.number_input(
            "半 FIRE 后目标月收入（元）",
            min_value=0,
            max_value=10_000_000,
            value=5_000,
            step=500,
            key="calculation_post_fire_income",
        )
    )
    exit_columns = st.columns(3)
    exit_months: list[YearMonth] = []
    for index, (column, default_offset) in enumerate(
        zip(exit_columns, (6, 10, 18), strict=True)
    ):
        with column:
            exit_months.append(
                _month_selectbox(
                    f"节点 {chr(65 + index)}",
                    month_options,
                    default_offset=min(default_offset, horizon_months),
                    key=f"calculation_exit_month_{index}",
                )
            )

    if len(set(exit_months)) != len(exit_months):
        st.error("三个退出节点需要选择不同月份。")
        return

    scenarios = _build_scenarios(
        exit_months=exit_months,
        post_fire_monthly_income_yuan=post_fire_monthly_income_yuan,
    )
    results = _evaluate_scenarios(
        scenarios=scenarios,
        points=points,
        withdrawal_rate_bps=round(withdrawal_rate * 100),
        state=st.session_state,
    )

    semi_fire_targets = [
        required_assets_for_budget(
            annual_budget_cents=get_annual_budget(
                year=point.month.year,
                state=st.session_state,
            ).total_cents,
            annual_active_income_cents=yuan_to_cents(
                post_fire_monthly_income_yuan * 12
            ),
            withdrawal_rate_bps=round(withdrawal_rate * 100),
        )
        for point in points
    ]
    full_fire_targets = [
        required_assets_for_budget(
            annual_budget_cents=get_annual_budget(
                year=point.month.year,
                state=st.session_state,
            ).total_cents,
            annual_active_income_cents=0,
            withdrawal_rate_bps=round(withdrawal_rate * 100),
        )
        for point in points
    ]

    st.subheader("3｜查看逐月资产增长")
    summary_columns = st.columns(4)
    summary_columns[0].metric("当前金融资产", format_wan(current_assets_cents))
    summary_columns[1].metric("月净储蓄", format_cny(yuan_to_cents(monthly_saving_yuan)))
    summary_columns[2].metric("规划提款率", format_bps(round(withdrawal_rate * 100)))
    summary_columns[3].metric("预测期末资产", format_wan(points[-1].closing_assets_cents))

    st.code(
        "月末资产 = 月初资产 + 月净储蓄 + 一次性收入 − 一次性支出",
        language=None,
    )
    st.plotly_chart(
        build_fire_runway_chart(
            points=points,
            semi_fire_targets=semi_fire_targets,
            full_fire_targets=full_fire_targets,
            scenario_results=results,
        ),
        width="stretch",
        config={"displayModeBar": False},
    )
    st.caption(
        "资产线只使用当前资产、月净储蓄和一次性事件，不假设投资收益；目标线由生活预算和半 FIRE 后收入反推。"
    )

    with st.expander("展开逐月计算明细"):
        st.dataframe(
            [_forecast_row(point) for point in points],
            hide_index=True,
            width="stretch",
        )

    st.subheader("4｜比较退出方案")
    if not results:
        st.warning("退出节点的生活预算必须大于 0，且退出资产不能为负数。")
        return

    result_columns = st.columns(len(results))
    for index, (column, result) in enumerate(zip(result_columns, results, strict=True)):
        with column:
            _render_result_card(chr(65 + index), result)

    st.dataframe(
        [_comparison_row(chr(65 + index), result) for index, result in enumerate(results)],
        hide_index=True,
        width="stretch",
    )
    _render_tradeoff_insights(results)

    st.subheader("5｜核对计算公式")
    st.write("每个数字都来自领域计算引擎。展开任一节点，可以逐项核对。")
    for index, result in enumerate(results):
        _render_formula_breakdown(chr(65 + index), result, withdrawal_rate)


def _render_forecast_inputs() -> tuple[date, int, int, float]:
    columns = st.columns(4)
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
        monthly_saving_yuan = int(
            st.number_input(
                "当前月净储蓄（元）",
                min_value=0,
                max_value=100_000_000,
                value=30_000,
                step=1_000,
                key="calculation_monthly_saving",
            )
        )
    with columns[3]:
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
    return as_of_date, horizon_months, monthly_saving_yuan, withdrawal_rate


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
    income_yuan: int,
    income_month: YearMonth,
    expense_yuan: int,
    expense_month: YearMonth,
) -> list[AssetEvent]:
    events: list[AssetEvent] = []
    if income_yuan:
        events.append(
            AssetEvent(
                id="calculation-income",
                plan_id="current-plan",
                event_month=income_month,
                event_type=AssetEventType.OTHER_INCOME,
                amount_cents=yuan_to_cents(income_yuan),
            )
        )
    if expense_yuan:
        events.append(
            AssetEvent(
                id="calculation-expense",
                plan_id="current-plan",
                event_month=expense_month,
                event_type=AssetEventType.EXTRA_EXPENSE,
                amount_cents=yuan_to_cents(expense_yuan),
            )
        )
    return events


def _build_scenarios(
    *,
    exit_months: Sequence[YearMonth],
    post_fire_monthly_income_yuan: int,
) -> list[Scenario]:
    return [
        Scenario(
            id=f"scenario-{chr(97 + index)}",
            plan_id="current-plan",
            name=f"节点 {chr(65 + index)}",
            exit_month=exit_month,
            post_fire_monthly_income_cents=yuan_to_cents(
                post_fire_monthly_income_yuan
            ),
        )
        for index, exit_month in enumerate(exit_months)
    ]


def _evaluate_scenarios(
    *,
    scenarios: Sequence[Scenario],
    points: Sequence[AssetPoint],
    withdrawal_rate_bps: int,
    state: MutableMapping[str, Any],
) -> list[ScenarioResult]:
    points_by_month = {point.month: point for point in points}
    evaluable = [
        scenario
        for scenario in scenarios
        if points_by_month[scenario.exit_month].closing_assets_cents >= 0
        and get_annual_budget(year=scenario.exit_month.year, state=state).total_cents
        > 0
    ]
    preliminary = [
        evaluate_scenario(
            scenario=scenario,
            exit_assets_cents=points_by_month[scenario.exit_month].closing_assets_cents,
            annual_budget_cents=get_annual_budget(
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
            exit_assets_cents=points_by_month[scenario.exit_month].closing_assets_cents,
            annual_budget_cents=get_annual_budget(
                year=scenario.exit_month.year,
                state=state,
            ).total_cents,
            withdrawal_rate_bps=withdrawal_rate_bps,
            candidate_results=preliminary,
        )
        for scenario in evaluable
    ]


def _forecast_row(point: AssetPoint) -> dict[str, str]:
    return {
        "月份": str(point.month),
        "月初资产": format_cny(point.opening_assets_cents),
        "+ 月净储蓄": format_cny(point.monthly_saving_cents),
        "+ 一次性收入": format_cny(point.one_time_income_cents),
        "− 一次性支出": format_cny(point.one_time_expense_cents),
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
