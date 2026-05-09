from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from ogmac.cli import main
from ogmac.state import State


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    secret = tmp_path / "client_secret.json"
    secret.write_text("{}")
    cfg = {
        "outlook": {"account": "user@example.com"},
        "google": {
            "account": "user@gmail.com",
            "client_secret_path": str(secret),
            "target_calendar_id": "cal123@group.calendar.google.com",
        },
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg))
    return p


@pytest.fixture()
def state_db(tmp_path: Path) -> Path:
    return tmp_path / "state.db"


def _run(argv: list[str], config_path: Path, state_db: Path) -> int:
    with (
        patch("ogmac.cli.setup_logging"),
        patch("ogmac.cli.Config.default_path", return_value=config_path),
        patch("ogmac.cli.state_db_path", return_value=state_db),
    ):
        return main(argv)


def test_pause_then_sync_skips_external_calls(config_path, state_db, tmp_path):
    assert _run(["pause"], config_path, state_db) == 0

    with (
        patch("ogmac.cli.get_google_credentials") as mock_gcreds,
        patch("ogmac.cli.get_graph_token") as mock_graph,
        patch("ogmac.cli.fetch_via_microsoft_graph") as mock_ms,
        patch("ogmac.cli.fetch_via_apple_calendar") as mock_apple,
        patch("ogmac.cli.fetch_target_events") as mock_gtarget,
    ):
        rc = _run(["sync"], config_path, state_db)

    assert rc == 0
    mock_gcreds.assert_not_called()
    mock_graph.assert_not_called()
    mock_ms.assert_not_called()
    mock_apple.assert_not_called()
    mock_gtarget.assert_not_called()


def test_unpause_then_sync_proceeds(config_path, state_db, tmp_path):
    _run(["pause"], config_path, state_db)
    assert _run(["unpause"], config_path, state_db) == 0

    mock_creds = MagicMock()

    with (
        patch("ogmac.cli.get_google_credentials", return_value=mock_creds) as mock_gcreds,
        patch("ogmac.cli.get_graph_token", return_value="tok"),
        patch("ogmac.cli.fetch_via_apple_calendar", return_value=[]) as mock_apple,
        patch("ogmac.cli.fetch_target_events", return_value=[]) as mock_gtarget,
        patch("ogmac.cli.reconcile", return_value=[]) as mock_reconcile,
    ):
        rc = _run(["sync"], config_path, state_db)

    assert rc == 0
    mock_gcreds.assert_called_once()
    mock_apple.assert_called_once()
    mock_gtarget.assert_called_once()
    mock_reconcile.assert_called_once()


def test_pause_is_idempotent(config_path, state_db):
    assert _run(["pause"], config_path, state_db) == 0
    assert _run(["pause"], config_path, state_db) == 0

    state = State(state_db)
    assert state.is_paused is True
    state.close()


def test_unpause_is_idempotent(config_path, state_db):
    assert _run(["unpause"], config_path, state_db) == 0

    state = State(state_db)
    assert state.is_paused is False
    state.close()
