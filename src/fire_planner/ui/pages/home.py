"""Planner overview page."""

from __future__ import annotations

import streamlit as st

from fire_planner.domain.scenario import required_assets_for_budget
from fire_planner.ui.formatters import format_wan
from fire_planner.ui.pages.assets import get_investable_assets_cents
from fire_planner.ui.pages.living import default_budget_year, get_annual_budget


def render_home_page() -> None:
    st.title("半 FIRE Planner")
    st.markdown("### 找到离开高强度工作的自由节点")
    st.write("先描述你想过的生活，再盘点可用于规划的金融资产。")

    year = int(st.session_state.get("budget_year", default_budget_year()))
    annual_budget = get_annual_budget(year=year, state=st.session_state)
    investable_assets_cents = get_investable_assets_cents(st.session_state)
    full_fire_assets_cents = required_assets_for_budget(
        annual_budget_cents=annual_budget.total_cents,
        annual_active_income_cents=0,
        withdrawal_rate_bps=350,
    )

    metric_columns = st.columns(3)
    metric_columns[0].metric(
        f"{year} 年生活预算",
        format_wan(annual_budget.total_cents),
    )
    metric_columns[1].metric(
        "可提款金融资产",
        format_wan(investable_assets_cents),
    )
    metric_columns[2].metric(
        "完全 FIRE 参考值",
        format_wan(full_fire_assets_cents),
        help="年度生活预算 ÷ 3.5%，仅作为参考。",
    )

    completed_steps = int(annual_budget.total_cents > 0) + int(
        investable_assets_cents > 0
    )
    st.progress(completed_steps / 3, text=f"规划资料完成 {completed_steps}/3")

    with st.container(border=True):
        st.subheader("开始你的规划")
        if annual_budget.total_cents > 0:
            st.success("生活预算已准备好")
        else:
            st.warning("请先填写想要的生活预算")
        if investable_assets_cents > 0:
            st.success("金融资产已准备好")
        else:
            st.warning("请填写当前金融资产")
        st.info("下一步将填写资产增长和退出方案，生成最早、平衡和高安全三个自由节点。")

    st.caption("3.5% 是长期规划提款率，不代表任何投资收益保证。")
