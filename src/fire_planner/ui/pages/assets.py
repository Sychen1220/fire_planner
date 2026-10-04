"""Asset and liability input page."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping

import streamlit as st

from fire_planner.domain.models import AssetHolding, AssetType
from fire_planner.domain.money import yuan_to_cents
from fire_planner.infrastructure.storage import save_form_state
from fire_planner.ui.formatters import format_wan


@dataclass(frozen=True, slots=True)
class AssetField:
    key: str
    label: str
    asset_type: AssetType


FINANCIAL_ASSET_FIELDS = (
    AssetField("cash", "现金", AssetType.CASH),
    AssetField("bank_deposit", "银行存款", AssetType.BANK_DEPOSIT),
    AssetField("fund", "基金", AssetType.FUND),
    AssetField("stock", "股票", AssetType.STOCK),
    AssetField("other_financial", "其他金融资产", AssetType.OTHER_FINANCIAL),
)


def asset_widget_key(field_key: str) -> str:
    return f"asset_{field_key}"


def build_financial_assets(
    state: MutableMapping[str, Any],
) -> list[AssetHolding]:
    return [
        AssetHolding(
            id=f"asset-{field.key}",
            plan_id="current-plan",
            asset_type=field.asset_type,
            amount_cents=yuan_to_cents(state.get(asset_widget_key(field.key), 0)),
        )
        for field in FINANCIAL_ASSET_FIELDS
    ]


def get_investable_assets_cents(state: MutableMapping[str, Any]) -> int:
    return sum(asset.amount_cents for asset in build_financial_assets(state))


def render_assets_page() -> None:
    st.title("我的资产")
    st.caption("金融资产用于半 FIRE 计算；自住房会单独展示，不计入可提款资产。")

    st.subheader("金融资产")
    financial_columns = st.columns(2)
    for index, field in enumerate(FINANCIAL_ASSET_FIELDS):
        with financial_columns[index % 2]:
            st.number_input(
                f"{field.label}（元）",
                min_value=0,
                max_value=10_000_000_000,
                value=0,
                step=10_000,
                key=asset_widget_key(field.key),
            )

    st.subheader("非金融资产")
    non_financial_columns = st.columns(2)
    with non_financial_columns[0]:
        st.number_input(
            "自住房估值（元）",
            min_value=0,
            max_value=100_000_000,
            value=0,
            step=10_000,
            key="asset_primary_residence",
        )
    with non_financial_columns[1]:
        st.number_input(
            "其他房产估值（元）",
            min_value=0,
            max_value=100_000_000,
            value=0,
            step=10_000,
            key="asset_other_property",
        )

    st.subheader("负债")
    liability_columns = st.columns(2)
    with liability_columns[0]:
        st.number_input(
            "房贷余额（元）",
            min_value=0,
            max_value=100_000_000,
            value=0,
            step=10_000,
            key="liability_mortgage_balance",
        )
        st.number_input(
            "房贷月供（元）",
            min_value=0,
            max_value=1_000_000,
            value=0,
            step=100,
            key="liability_mortgage_payment",
        )
    with liability_columns[1]:
        st.number_input(
            "房贷年利率（%）",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=0.1,
            key="liability_mortgage_rate",
        )
        st.number_input(
            "剩余期限（月）",
            min_value=0,
            max_value=600,
            value=0,
            step=1,
            key="liability_mortgage_months",
        )

    investable_assets_cents = get_investable_assets_cents(st.session_state)
    non_financial_assets_cents = yuan_to_cents(
        st.session_state.get("asset_primary_residence", 0)
        + st.session_state.get("asset_other_property", 0)
    )
    liabilities_cents = yuan_to_cents(
        st.session_state.get("liability_mortgage_balance", 0)
    )
    net_worth_cents = (
        investable_assets_cents
        + non_financial_assets_cents
        - liabilities_cents
    )

    st.divider()
    metric_columns = st.columns(3)
    metric_columns[0].metric("可提款金融资产", format_wan(investable_assets_cents))
    metric_columns[1].metric("非金融资产", format_wan(non_financial_assets_cents))
    metric_columns[2].metric("估算净资产", format_wan(net_worth_cents))

    if st.session_state.get("liability_mortgage_balance", 0) > 0:
        st.info("房贷余额不会直接从 FIRE 资产中扣除，请确认房贷月供已包含在生活预算中。")

    if st.button("保存资产信息", type="primary", width="stretch"):
        save_form_state(st.session_state)
        st.success("资产信息已保存。")
