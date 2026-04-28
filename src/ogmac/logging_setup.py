from __future__ import annotations

import logging
import logging.handlers
import os
import time
from pathlib import Path


def log_path() -> Path:
    p = Path.home() / "Library" / "Logs" / "ogmac" / "sync.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def setup_logging(debug: bool = False) -> None:
    target = log_path()

    root = logging.getLogger()

    for handler in root.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            if handler.baseFilename == str(target):
                return

    level = logging.DEBUG if (debug or os.environ.get("OGMAC_DEBUG") == "1") else logging.INFO
    root.setLevel(level)

    handler = logging.handlers.RotatingFileHandler(
        target,
        maxBytes=1_000_000,
        backupCount=10,
        encoding="utf-8",
    )
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)sZ %(levelname)-5s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = time.gmtime  # type: ignore[assignment]
    handler.setFormatter(formatter)

    root.addHandler(handler)
