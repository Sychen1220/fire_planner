"""Small SQLite-backed store for the local Streamlit plan."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, MutableMapping


SESSION_STATE_KEYS = (
    "budget_year",
    "asset_cash",
    "asset_bank_deposit",
    "asset_fund",
    "asset_stock",
    "asset_other_financial",
    "asset_primary_residence",
    "asset_other_property",
    "liability_mortgage_balance",
    "liability_mortgage_payment",
    "liability_mortgage_rate",
    "liability_mortgage_months",
)


def database_path() -> Path:
    configured_path = os.environ.get("FIRE_PLANNER_DB_PATH")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path(__file__).resolve().parents[3] / "fire_planner.sqlite3"


def load_persisted_state(state: MutableMapping[str, Any]) -> bool:
    """Load the last saved form values into session state once per session."""
    if state.get("_persistence_loaded"):
        return False
    state["_persistence_loaded"] = True
    saved_values = _read_values(database_path())
    for key, value in saved_values.items():
        state.setdefault(key, value)
    return bool(saved_values)


def save_form_state(state: MutableMapping[str, Any]) -> None:
    values = {
        key: value
        for key, value in state.items()
        if (key in SESSION_STATE_KEYS or key.startswith("budget_"))
        and isinstance(value, (int, float, str, bool))
    }
    _write_values(database_path(), values)


def _read_values(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS form_state "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        rows = connection.execute("SELECT key, value FROM form_state").fetchall()
    return {key: json.loads(value) for key, value in rows}


def _write_values(path: Path, values: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS form_state "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO form_state(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [(key, json.dumps(value, ensure_ascii=False)) for key, value in values.items()],
        )
        connection.commit()
