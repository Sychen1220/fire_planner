"""Plotly chart builders."""

from __future__ import annotations

from typing import Sequence

import plotly.graph_objects as go

from fire_planner.domain.forecast import AssetPoint
from fire_planner.domain.models import ScenarioResult, ScenarioStatus


STATUS_COLORS = {
    ScenarioStatus.GREEN: "#1f9d55",
    ScenarioStatus.YELLOW: "#d69e2e",
    ScenarioStatus.ORANGE: "#dd6b20",
    ScenarioStatus.RED: "#c53030",
}


def build_fire_runway_chart(
    *,
    initial_assets_cents: int,
    points: Sequence[AssetPoint],
    semi_fire_targets: Sequence[int],
    full_fire_targets: Sequence[int],
    scenario_results: Sequence[ScenarioResult],
) -> go.Figure:
    """Build the FIRE runway from values already produced by the domain engine."""
    if len(points) != len(semi_fire_targets) or len(points) != len(full_fire_targets):
        raise ValueError("chart target series must align with forecast points")

    months = ["当前资产"] + [str(point.month) for point in points]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=months,
            y=[_to_wan(initial_assets_cents)]
            + [_to_wan(point.closing_assets_cents) for point in points],
            mode="lines+markers",
            name="月末金融资产",
            line={"color": "#ff6b35", "width": 3},
            hovertemplate="%{x}<br>金融资产 %{y:,.2f} 万<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=months,
            y=[_to_wan(semi_fire_targets[0])] + [
                _to_wan(value) for value in semi_fire_targets
            ],
            mode="lines",
            name="半 FIRE 目标线",
            line={"color": "#2b6cb0", "width": 2, "dash": "dash"},
            hovertemplate="%{x}<br>目标资产 %{y:,.2f} 万<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=months,
            y=[_to_wan(full_fire_targets[0])] + [
                _to_wan(value) for value in full_fire_targets
            ],
            mode="lines",
            name="完全 FIRE 参考线",
            line={"color": "#718096", "width": 2, "dash": "dot"},
            hovertemplate="%{x}<br>参考资产 %{y:,.2f} 万<extra></extra>",
        )
    )

    if scenario_results:
        figure.add_trace(
            go.Scatter(
                x=[str(result.exit_month) for result in scenario_results],
                y=[_to_wan(result.exit_assets_cents) for result in scenario_results],
                mode="markers+text",
                name="退出节点",
                text=[result.scenario_id[-1].upper() for result in scenario_results],
                textposition="top center",
                marker={
                    "color": [STATUS_COLORS[result.status] for result in scenario_results],
                    "size": 13,
                    "line": {"color": "white", "width": 2},
                },
                customdata=[
                    [
                        f"{result.coverage_ratio:.1%}",
                        _to_wan(result.annual_available_cents),
                    ]
                    for result in scenario_results
                ],
                hovertemplate=(
                    "%{x}<br>退出资产 %{y:,.2f} 万"
                    "<br>年度可支配 %{customdata[1]:,.2f} 万"
                    "<br>覆盖率 %{customdata[0]}<extra></extra>"
                ),
            )
        )

    figure.update_layout(
        height=460,
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.12, "x": 0},
        xaxis_title="月份",
        yaxis_title="金额（万元）",
    )
    return figure


def _to_wan(cents: int) -> float:
    return cents / 1_000_000
