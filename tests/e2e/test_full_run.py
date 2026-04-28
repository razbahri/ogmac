from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ogmac.models import Action, ActionKind, SourceEvent, TargetEvent
from ogmac.state import State


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _make_source(instance_id: str, last_modified: datetime, **kwargs) -> SourceEvent:
    defaults = dict(
        outlook_id=f"oid-{instance_id}",
        instance_id=instance_id,
        subject="Meeting",
        start_utc=_utc(2026, 4, 28, 10, 0),
        end_utc=_utc(2026, 4, 28, 11, 0),
        location=None,
        body_text="",
        last_modified=last_modified,
        is_cancelled=False,
    )
    defaults.update(kwargs)
    return SourceEvent(**defaults)


def _make_target(instance_id: str, google_id: str, last_synced: datetime) -> TargetEvent:
    return TargetEvent(
        google_id=google_id,
        etag="etag",
        instance_id=instance_id,
        last_synced_outlook_modified=last_synced,
    )


def _write_config(path: Path, calendar_id: str = "cal123", read_method: str = "apple_calendar") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        textwrap.dedent(f"""\
        outlook:
          account: test@example.com
          source_calendar: default
          read_method: {read_method}
        google:
          account: test@gmail.com
          client_secret_path: /tmp/fake_secret.json
          target_calendar_id: {calendar_id}
        """)
    )


@pytest.fixture(autouse=True)
def _no_real_logging():
    with patch("ogmac.cli.setup_logging"):
        yield


@pytest.fixture()
def tmp_cfg(tmp_path: Path) -> Path:
    cfg_path = tmp_path / "config.yaml"
    _write_config(cfg_path)
    return cfg_path


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "state.db"


def _patch_paths(monkeypatch, tmp_cfg: Path, tmp_db: Path):
    monkeypatch.setattr("ogmac.cli.state_db_path", lambda: tmp_db)
    monkeypatch.setattr("ogmac.cli.Config.default_path", lambda: tmp_cfg)


class TestCleanSyncThreeActions:
    def test_clean_sync(self, monkeypatch, tmp_cfg, tmp_db):
        _patch_paths(monkeypatch, tmp_cfg, tmp_db)

        t_old = _utc(2026, 4, 1, 0, 0)
        t_new = _utc(2026, 4, 20, 0, 0)

        # 4 sources, 4 targets → 3 non-SKIP actions (UPDATE + CREATE + DELETE)
        # id1: src t_new, tgt t_new → SKIP
        # id2: src t_new, tgt t_new → SKIP
        # id3: src t_new, tgt t_old → UPDATE
        # id4: src only           → CREATE
        # id_del: tgt only        → DELETE
        sources = [
            _make_source("id1", t_new),
            _make_source("id2", t_new),
            _make_source("id3", t_new),
            _make_source("id4", t_new),
        ]
        targets = [
            _make_target("id1", "gid1", t_new),
            _make_target("id2", "gid2", t_new),
            _make_target("id3", "gid3", t_old),
            _make_target("id_del", "gid_del", t_old),
        ]

        mock_creds = MagicMock()
        apply_call_kinds = []

        def fake_apply(creds, cal_id, action):
            apply_call_kinds.append(action.kind)
            if action.kind is ActionKind.CREATE:
                return "gid4_new"
            if action.kind is ActionKind.UPDATE:
                return action.target.google_id
            return None

        with (
            patch("ogmac.cli.get_graph_token", return_value="fake_token"),
            patch("ogmac.cli.get_google_credentials", return_value=mock_creds),
            patch("ogmac.cli.fetch_via_apple_calendar", return_value=sources),
            patch("ogmac.cli.fetch_target_events", return_value=targets),
            patch("ogmac.cli.find_orphan_by_instance_id", return_value=None),
            patch("ogmac.cli.apply_action", side_effect=fake_apply) as mock_apply,
        ):
            from ogmac.cli import main
            exit_code = main(["sync"])

        assert exit_code == 0
        assert mock_apply.call_count == 3

        kinds_applied = sorted(k.value for k in apply_call_kinds)
        assert kinds_applied == ["CREATE", "DELETE", "UPDATE"]

        state = State(tmp_db)
        assert state.consecutive_failures == 0
        assert state.get_run_state("last_success_at") is not None
        state.close()


class TestDisabledStateShortCircuit:
    def test_disabled_exits_without_api_calls(self, monkeypatch, tmp_cfg, tmp_db):
        _patch_paths(monkeypatch, tmp_cfg, tmp_db)

        state = State(tmp_db)
        state.disable("pre-populated test")
        state.close()

        with (
            patch("ogmac.cli.get_graph_token") as mock_token,
            patch("ogmac.cli.get_google_credentials") as mock_creds,
            patch("ogmac.cli.fetch_via_apple_calendar") as mock_fetch_src,
            patch("ogmac.cli.fetch_target_events") as mock_fetch_tgt,
        ):
            from ogmac.cli import main
            exit_code = main(["sync"])

        assert exit_code == 0
        mock_token.assert_not_called()
        mock_creds.assert_not_called()
        mock_fetch_src.assert_not_called()
        mock_fetch_tgt.assert_not_called()


class TestTokenRefreshFailure:
    def test_token_failure_increments_counter_and_notifies(self, monkeypatch, tmp_cfg, tmp_db):
        _patch_paths(monkeypatch, tmp_cfg, tmp_db)

        from ogmac.auth import TokenRefreshError

        with (
            patch("ogmac.cli.get_google_credentials", side_effect=TokenRefreshError("expired")),
            patch("ogmac.cli.fetch_via_apple_calendar") as mock_fetch_src,
            patch("ogmac.cli.fetch_target_events") as mock_fetch_tgt,
            patch("ogmac.cli.notify") as mock_notify,
        ):
            from ogmac.cli import main
            exit_code = main(["sync"])

        assert exit_code == 1
        mock_fetch_src.assert_not_called()
        mock_fetch_tgt.assert_not_called()

        state = State(tmp_db)
        assert state.consecutive_failures == 1
        state.close()

        assert mock_notify.call_count == 1
        notify_kwargs = mock_notify.call_args
        assert notify_kwargs.kwargs.get("sticky", False) is False or (
            len(notify_kwargs.args) >= 3 and notify_kwargs.args[2] is False
        )


class TestAutoDisableThreshold:
    def test_fifth_failure_disables_and_fires_sticky(self, monkeypatch, tmp_cfg, tmp_db):
        _patch_paths(monkeypatch, tmp_cfg, tmp_db)

        state = State(tmp_db)
        for _ in range(4):
            state.increment_failures()
        state.close()

        from ogmac.auth import TokenRefreshError

        with (
            patch("ogmac.cli.get_google_credentials", side_effect=TokenRefreshError("still broken")),
            patch("ogmac.cli.notify") as mock_notify,
        ):
            from ogmac.cli import main
            exit_code = main(["sync"])

        assert exit_code == 1

        state = State(tmp_db)
        assert state.consecutive_failures == 5
        assert state.is_disabled is True
        state.close()

        assert mock_notify.call_count == 1
        notify_call = mock_notify.call_args
        assert notify_call.kwargs.get("sticky") is True or (
            len(notify_call.args) >= 3 and notify_call.args[2] is True
        )


class TestMicrosoftGraphBackend:
    def test_graph_backend_dispatches_to_graph_reader_and_uses_token(self, monkeypatch, tmp_path, tmp_db):
        cfg_path = tmp_path / "config.yaml"
        _write_config(cfg_path, read_method="microsoft_graph")
        monkeypatch.setattr("ogmac.cli.state_db_path", lambda: tmp_db)
        monkeypatch.setattr("ogmac.cli.Config.default_path", lambda: cfg_path)

        sources = [_make_source("g1", _utc(2026, 4, 20, 0, 0))]
        mock_creds = MagicMock()

        with (
            patch("ogmac.cli.get_graph_token", return_value="real_token") as mock_token,
            patch("ogmac.cli.get_google_credentials", return_value=mock_creds),
            patch("ogmac.cli.fetch_via_microsoft_graph", return_value=sources) as mock_graph_reader,
            patch("ogmac.cli.fetch_via_apple_calendar") as mock_apple_reader,
            patch("ogmac.cli.fetch_target_events", return_value=[]),
            patch("ogmac.cli.find_orphan_by_instance_id", return_value=None),
            patch("ogmac.cli.apply_action", return_value="new_gid"),
        ):
            from ogmac.cli import main
            exit_code = main(["sync"])

        assert exit_code == 0
        mock_token.assert_called_once()
        mock_graph_reader.assert_called_once()
        assert mock_graph_reader.call_args.args[0] == "real_token"
        mock_apple_reader.assert_not_called()


class TestDuplicateAdoption:
    def test_orphan_becomes_update_not_create(self, monkeypatch, tmp_cfg, tmp_db):
        _patch_paths(monkeypatch, tmp_cfg, tmp_db)

        t_old = _utc(2026, 4, 1, 0, 0)
        t_new = _utc(2026, 4, 20, 0, 0)

        orphan_instance_id = "orphan-id"
        orphan_google_id = "orphan-gid"

        sources = [_make_source(orphan_instance_id, t_new)]
        targets: list[TargetEvent] = []

        orphan_target = _make_target(orphan_instance_id, orphan_google_id, t_old)
        mock_creds = MagicMock()

        applied_actions: list[Action] = []

        def fake_apply(creds, cal_id, action):
            applied_actions.append(action)
            if action.kind is ActionKind.UPDATE:
                return action.target.google_id
            return "new_gid"

        with (
            patch("ogmac.cli.get_graph_token", return_value="tok"),
            patch("ogmac.cli.get_google_credentials", return_value=mock_creds),
            patch("ogmac.cli.fetch_via_apple_calendar", return_value=sources),
            patch("ogmac.cli.fetch_target_events", return_value=targets),
            patch("ogmac.cli.find_orphan_by_instance_id", return_value=orphan_target) as mock_orphan,
            patch("ogmac.cli.apply_action", side_effect=fake_apply),
        ):
            from ogmac.cli import main
            exit_code = main(["sync"])

        assert exit_code == 0
        mock_orphan.assert_called_once()

        assert len(applied_actions) == 1
        assert applied_actions[0].kind is ActionKind.UPDATE
        assert applied_actions[0].target.google_id == orphan_google_id
        assert applied_actions[0].source.instance_id == orphan_instance_id
