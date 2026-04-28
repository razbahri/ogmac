from __future__ import annotations

import logging
import logging.handlers
import time
from pathlib import Path

import pytest

from ogmac.logging_setup import log_path, setup_logging


@pytest.fixture(autouse=True)
def clean_root_logger():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    for h in list(root.handlers):
        if h not in original_handlers:
            root.removeHandler(h)
            h.close()
    root.setLevel(original_level)


@pytest.fixture()
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    return tmp_path


class TestLogPath:
    def test_returns_correct_path(self, fake_home: Path):
        p = log_path()
        assert p == fake_home / "Library" / "Logs" / "ogmac" / "sync.log"

    def test_creates_parent_directory(self, fake_home: Path):
        p = log_path()
        assert p.parent.exists()

    def test_idempotent_when_called_twice(self, fake_home: Path):
        p1 = log_path()
        p2 = log_path()
        assert p1 == p2


class TestSetupLogging:
    def test_adds_rotating_file_handler(self, fake_home: Path):
        setup_logging()
        root = logging.getLogger()
        handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(handlers) == 1

    def test_handler_points_to_correct_path(self, fake_home: Path):
        setup_logging()
        root = logging.getLogger()
        handler = next(h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
        expected = str(fake_home / "Library" / "Logs" / "ogmac" / "sync.log")
        assert handler.baseFilename == expected

    def test_handler_max_bytes(self, fake_home: Path):
        setup_logging()
        root = logging.getLogger()
        handler = next(h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
        assert handler.maxBytes == 1_000_000

    def test_handler_backup_count(self, fake_home: Path):
        setup_logging()
        root = logging.getLogger()
        handler = next(h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
        assert handler.backupCount == 10

    def test_default_level_is_info(self, fake_home: Path):
        setup_logging()
        assert logging.getLogger().level == logging.INFO

    def test_debug_arg_sets_debug_level(self, fake_home: Path):
        setup_logging(debug=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_debug_env_var_sets_debug_level(self, fake_home: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OGMAC_DEBUG", "1")
        setup_logging()
        assert logging.getLogger().level == logging.DEBUG

    def test_debug_env_var_off_keeps_info(self, fake_home: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OGMAC_DEBUG", "0")
        setup_logging()
        assert logging.getLogger().level == logging.INFO

    def test_idempotent_no_duplicate_handlers(self, fake_home: Path):
        setup_logging()
        setup_logging()
        root = logging.getLogger()
        rotating = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(rotating) == 1

    def test_formatter_uses_utc(self, fake_home: Path):
        setup_logging()
        root = logging.getLogger()
        handler = next(h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
        assert handler.formatter is not None
        assert handler.formatter.converter is time.gmtime

    def test_formatter_format_string(self, fake_home: Path):
        setup_logging()
        root = logging.getLogger()
        handler = next(h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
        assert handler.formatter is not None
        assert "%(asctime)s" in handler.formatter._fmt
        assert "%(levelname)" in handler.formatter._fmt
        assert "%(name)s" in handler.formatter._fmt
        assert "%(message)s" in handler.formatter._fmt

    def test_formatter_datefmt(self, fake_home: Path):
        setup_logging()
        root = logging.getLogger()
        handler = next(h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
        assert handler.formatter is not None
        assert handler.formatter.datefmt == "%Y-%m-%dT%H:%M:%S"
