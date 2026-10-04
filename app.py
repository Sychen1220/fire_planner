"""Streamlit application entry point."""

import streamlit as st


def main() -> None:
    st.set_page_config(page_title="半 FIRE Planner", page_icon="🔥", layout="wide")
    st.title("半 FIRE Planner")
    st.caption("找到离开高强度工作的自由节点。")


if __name__ == "__main__":
    main()

