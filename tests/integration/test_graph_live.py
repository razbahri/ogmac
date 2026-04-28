from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

OGMAC_LIVE = os.environ.get("OGMAC_LIVE") == "1"

pytestmark = pytest.mark.skipif(not OGMAC_LIVE, reason="OGMAC_LIVE=1 not set")


@pytest.mark.skipif(not OGMAC_LIVE, reason="OGMAC_LIVE=1 not set")
def test_fetch_source_events_live():
    from ogmac.auth import get_graph_token
    from ogmac.config import Config
    from ogmac.outlook import fetch_source_events

    config_path = Path.home() / ".config" / "ogmac" / "config.yaml"
    config = Config.load(config_path)
    token = get_graph_token(config)

    now = datetime.now(tz=timezone.utc)
    start = now
    end = now + timedelta(days=7)

    events = fetch_source_events(token, "default", start, end)

    assert isinstance(events, list)
