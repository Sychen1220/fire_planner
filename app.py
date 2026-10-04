"""Streamlit application entry point."""

import sys
from pathlib import Path

import streamlit as st

SRC_DIRECTORY = Path(__file__).resolve().parent / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from fire_planner.ui.pages.assets import render_assets_page
from fire_planner.ui.pages.calculation import render_calculation_page
from fire_planner.ui.pages.home import render_home_page
from fire_planner.ui.pages.living import render_living_page


PAGE_RENDERERS = {
    "首页": render_home_page,
    "我的生活": render_living_page,
    "我的资产": render_assets_page,
    "开始测算": render_calculation_page,
}


def main() -> None:
    st.set_page_config(page_title="半 FIRE Planner", page_icon="🔥", layout="wide")
    st.markdown(
        """
        <style>
        .block-container {max-width: 1120px; padding-top: 2rem; padding-bottom: 4rem;}
        [data-testid="stMetric"] {
            background: rgba(255, 107, 53, 0.06);
            border: 1px solid rgba(255, 107, 53, 0.16);
            border-radius: 14px;
            padding: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("## 🔥 半 FIRE Planner")
        st.caption("资产 + 低强度收入，换取生活选择权。")
        selected_page = st.radio(
            "导航",
            options=list(PAGE_RENDERERS),
            label_visibility="collapsed",
            key="selected_page",
        )
        st.divider()
        st.caption("当前规划提款率：3.50%")

    PAGE_RENDERERS[selected_page]()


if __name__ == "__main__":
    main()
