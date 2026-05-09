from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ogmac.config import Config, ConfigError


def write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.dump(data))
    return path


def minimal_data(tmp_path: Path) -> dict:
    secret = tmp_path / "secret.json"
    secret.touch()
    return {
        "outlook": {"account": "user@example.com"},
        "google": {
            "account": "user@gmail.com",
            "client_secret_path": str(secret),
            "target_calendar_id": "cal123@group.calendar.google.com",
        },
    }


# ── valid config ───────────────────────────────────────────────────────────

def test_valid_config_loads(tmp_path):
    data = minimal_data(tmp_path)
    cfg = Config.load(write_yaml(tmp_path / "config.yaml", data))
    assert cfg.outlook.account == "user@example.com"
    assert cfg.google.account == "user@gmail.com"
    assert cfg.google.target_calendar_id == "cal123@group.calendar.google.com"


def test_defaults_applied(tmp_path):
    data = minimal_data(tmp_path)
    cfg = Config.load(write_yaml(tmp_path / "config.yaml", data))
    assert cfg.outlook.source_calendar == "default"
    assert cfg.outlook.read_method == "apple_calendar"
    assert cfg.sync.window_past_days == 1
    assert cfg.sync.window_future_days == 30
    assert not hasattr(cfg.sync, "interval_seconds")
    assert cfg.privacy.copy_subject is True
    assert cfg.privacy.copy_location is True
    assert cfg.privacy.copy_body is True
    assert cfg.privacy.copy_attendees is False
    assert cfg.failure.max_consecutive_before_disable == 5
    assert cfg.failure.notify_on_failure is True


def test_explicit_values_override_defaults(tmp_path):
    data = minimal_data(tmp_path)
    data["sync"] = {"window_past_days": 2, "window_future_days": 60}
    data["failure"] = {"max_consecutive_before_disable": 3, "notify_on_failure": False}
    cfg = Config.load(write_yaml(tmp_path / "config.yaml", data))
    assert cfg.sync.window_past_days == 2
    assert cfg.sync.window_future_days == 60
    assert cfg.failure.max_consecutive_before_disable == 3
    assert cfg.failure.notify_on_failure is False


# ── path expansion ─────────────────────────────────────────────────────────

def test_tilde_expansion_in_client_secret_path(tmp_path):
    data = minimal_data(tmp_path)
    data["google"]["client_secret_path"] = "~/.config/ogmac/google_client_secret.json"
    cfg = Config.load(write_yaml(tmp_path / "config.yaml", data))
    assert not str(cfg.google.client_secret_path).startswith("~")
    assert cfg.google.client_secret_path.is_absolute()


# ── missing required fields ────────────────────────────────────────────────

def test_missing_outlook_account_raises(tmp_path):
    data = minimal_data(tmp_path)
    del data["outlook"]["account"]
    with pytest.raises(ValidationError):
        Config.load(write_yaml(tmp_path / "config.yaml", data))


def test_missing_google_section_raises(tmp_path):
    data = minimal_data(tmp_path)
    del data["google"]
    with pytest.raises(ValidationError):
        Config.load(write_yaml(tmp_path / "config.yaml", data))


def test_missing_google_target_calendar_id_raises(tmp_path):
    data = minimal_data(tmp_path)
    del data["google"]["target_calendar_id"]
    with pytest.raises(ValidationError):
        Config.load(write_yaml(tmp_path / "config.yaml", data))


# ── copy_attendees locked false ────────────────────────────────────────────

def test_copy_attendees_true_rejected(tmp_path):
    data = minimal_data(tmp_path)
    data["privacy"] = {"copy_attendees": True}
    with pytest.raises(ValidationError) as exc_info:
        Config.load(write_yaml(tmp_path / "config.yaml", data))
    assert "copy_attendees" in str(exc_info.value).lower()


def test_copy_attendees_false_accepted(tmp_path):
    data = minimal_data(tmp_path)
    data["privacy"] = {"copy_attendees": False}
    cfg = Config.load(write_yaml(tmp_path / "config.yaml", data))
    assert cfg.privacy.copy_attendees is False


# ── read_method ────────────────────────────────────────────────────────────

def test_read_method_microsoft_graph_accepted(tmp_path):
    data = minimal_data(tmp_path)
    data["outlook"]["read_method"] = "microsoft_graph"
    cfg = Config.load(write_yaml(tmp_path / "config.yaml", data))
    assert cfg.outlook.read_method == "microsoft_graph"


def test_read_method_apple_calendar_accepted(tmp_path):
    data = minimal_data(tmp_path)
    data["outlook"]["read_method"] = "apple_calendar"
    cfg = Config.load(write_yaml(tmp_path / "config.yaml", data))
    assert cfg.outlook.read_method == "apple_calendar"


def test_read_method_invalid_rejected(tmp_path):
    data = minimal_data(tmp_path)
    data["outlook"]["read_method"] = "carrier_pigeon"
    with pytest.raises(ValidationError):
        Config.load(write_yaml(tmp_path / "config.yaml", data))


# ── interval_seconds deprecation ──────────────────────────────────────────

def test_legacy_interval_seconds_dropped_silently(tmp_path):
    data = minimal_data(tmp_path)
    data["sync"] = {"window_past_days": 1, "window_future_days": 30, "interval_seconds": 900}
    with pytest.warns(DeprecationWarning, match="interval_seconds"):
        cfg = Config.load(write_yaml(tmp_path / "config.yaml", data))
    assert not hasattr(cfg.sync, "interval_seconds")
    assert cfg.sync.window_past_days == 1
    assert cfg.sync.window_future_days == 30


def test_no_warning_without_interval_seconds(tmp_path):
    data = minimal_data(tmp_path)
    import warnings as _warnings
    with _warnings.catch_warnings():
        _warnings.simplefilter("error", DeprecationWarning)
        cfg = Config.load(write_yaml(tmp_path / "config.yaml", data))
    assert cfg.sync.window_past_days == 1


# ── file-not-found ─────────────────────────────────────────────────────────

def test_config_file_not_found_raises_config_error(tmp_path):
    with pytest.raises(ConfigError):
        Config.load(tmp_path / "does_not_exist.yaml")


# ── default_path ───────────────────────────────────────────────────────────

def test_default_path():
    p = Config.default_path()
    assert p == Path.home() / ".config" / "ogmac" / "config.yaml"
