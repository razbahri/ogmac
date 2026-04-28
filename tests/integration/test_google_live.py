from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ogmac.auth import get_google_credentials
from ogmac.google import apply_action, fetch_target_events
from ogmac.models import Action, ActionKind, SourceEvent

pytestmark = pytest.mark.skipif(
    os.environ.get("OGMAC_LIVE") != "1",
    reason="Set OGMAC_LIVE=1 to run live integration tests",
)

_TEST_CALENDAR_NAME = "ogmac-test"


def _load_config():
    from ogmac.config import Config
    config_path = Path.home() / ".config" / "ogmac" / "config.yaml"
    return Config.load(config_path)


def _find_test_calendar(service):
    response = service.calendarList().list().execute()
    for entry in response.get("items", []):
        if entry.get("summary") == _TEST_CALENDAR_NAME:
            return entry["id"]
    return None


def _build_service(credentials):
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _source_event() -> SourceEvent:
    now = datetime.now(timezone.utc)
    return SourceEvent(
        outlook_id="live-test-outlook-id",
        instance_id="live-test-instance-id",
        subject="ogmac live test event",
        start_utc=now + timedelta(hours=1),
        end_utc=now + timedelta(hours=2),
        location="Test Location",
        body_text="Created by ogmac integration test.",
        last_modified=now,
        is_cancelled=False,
    )


def test_create_fetch_delete():
    config = _load_config()
    creds = get_google_credentials(config)
    service = _build_service(creds)

    calendar_id = _find_test_calendar(service)
    if calendar_id is None:
        pytest.skip(
            f"No calendar named '{_TEST_CALENDAR_NAME}' found. "
            "Create it in Google Calendar before running live tests."
        )

    src = _source_event()
    now = datetime.now(timezone.utc)
    window_start = now
    window_end = now + timedelta(hours=3)

    create_action = Action(kind=ActionKind.CREATE, source=src, target=None)
    new_id = apply_action(creds, calendar_id, create_action)
    assert new_id is not None, "CREATE should return a google_id"

    time.sleep(1)

    targets = fetch_target_events(creds, calendar_id, window_start, window_end)
    matching = [t for t in targets if t.google_id == new_id]
    assert len(matching) == 1, f"Expected to find created event {new_id} in fetch results"

    target = matching[0]
    assert target.instance_id == src.instance_id

    delete_action = Action(kind=ActionKind.DELETE, source=None, target=target)
    result = apply_action(creds, calendar_id, delete_action)
    assert result is None

    time.sleep(1)

    targets_after = fetch_target_events(creds, calendar_id, window_start, window_end)
    still_present = [t for t in targets_after if t.google_id == new_id]
    assert len(still_present) == 0, f"Event {new_id} should be deleted"
