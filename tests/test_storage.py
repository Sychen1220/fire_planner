from __future__ import annotations

from pathlib import Path

from fire_planner.infrastructure.storage import load_persisted_state, save_form_state


def test_form_state_round_trips_through_sqlite(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "planner.sqlite3"
    monkeypatch.setenv("FIRE_PLANNER_DB_PATH", str(database))

    save_form_state(
        {
            "budget_year": 2027,
            "budget_2027_travel": 50000,
            "asset_cash": 1600000,
            "ignored": object(),
        }
    )

    restored: dict[str, object] = {}
    assert load_persisted_state(restored) is True
    assert restored["budget_year"] == 2027
    assert restored["budget_2027_travel"] is not None
    assert restored["asset_cash"] == 1600000
    assert "ignored" not in restored


def test_load_persisted_state_only_reads_once(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "planner.sqlite3"
    monkeypatch.setenv("FIRE_PLANNER_DB_PATH", str(database))
    state = {"_persistence_loaded": True, "asset_cash": 123}

    assert load_persisted_state(state) is False
    assert state["asset_cash"] == 123
