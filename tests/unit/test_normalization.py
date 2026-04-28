from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


from ogmac.outlook import normalize_event

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _utc(year, month, day, hour=0, minute=0, second=0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class TestSingleNonRecurring:
    def setup_method(self):
        page = load_fixture("graph_calendarview_page.json")
        self.raw = page["value"][0]
        self.ev = normalize_event(self.raw)

    def test_outlook_id_is_event_id_when_no_master(self):
        assert self.ev.outlook_id == self.raw["id"]

    def test_instance_id_is_event_id(self):
        assert self.ev.instance_id == self.raw["id"]

    def test_subject(self):
        assert self.ev.subject == "Q2 Planning"

    def test_start_utc(self):
        assert self.ev.start_utc == _utc(2026, 5, 1, 9, 0, 0)

    def test_end_utc(self):
        assert self.ev.end_utc == _utc(2026, 5, 1, 10, 0, 0)

    def test_location(self):
        assert self.ev.location == "Conference Room A"

    def test_body_html_stripped(self):
        assert "<" not in self.ev.body_text
        assert "Quarterly planning session" in self.ev.body_text

    def test_last_modified(self):
        assert self.ev.last_modified == _utc(2026, 4, 20, 14, 30, 0)

    def test_is_cancelled_false(self):
        assert self.ev.is_cancelled is False

    def test_start_utc_has_timezone(self):
        assert self.ev.start_utc.tzinfo is not None


class TestRecurringOccurrence:
    def setup_method(self):
        page = load_fixture("graph_recurring_expanded.json")
        self.raw_occ1 = page["value"][0]
        self.raw_occ2 = page["value"][1]
        self.ev1 = normalize_event(self.raw_occ1)
        self.ev2 = normalize_event(self.raw_occ2)

    def test_outlook_id_is_series_master(self):
        assert self.ev1.outlook_id == "CCMkAGE1master=="
        assert self.ev2.outlook_id == "CCMkAGE1master=="

    def test_instance_id_is_occurrence_id(self):
        assert self.ev1.instance_id == "CCMkAGE1instance001=="
        assert self.ev2.instance_id == "CCMkAGE1instance002=="

    def test_outlook_id_differs_from_instance_id(self):
        assert self.ev1.outlook_id != self.ev1.instance_id


class TestCancelledOccurrence:
    def setup_method(self):
        page = load_fixture("graph_recurring_expanded.json")
        self.raw = page["value"][2]
        self.ev = normalize_event(self.raw)

    def test_is_cancelled_true(self):
        assert self.ev.is_cancelled is True

    def test_outlook_id_is_series_master(self):
        assert self.ev.outlook_id == "CCMkAGE1master=="

    def test_instance_id_is_occurrence_id(self):
        assert self.ev.instance_id == "CCMkAGE1instance003=="


class TestHtmlBodyStripping:
    def test_html_tags_removed(self):
        raw = {
            "id": "test-id",
            "subject": "Test",
            "start": {"dateTime": "2026-05-01T10:00:00.0000000", "timeZone": "UTC"},
            "end": {"dateTime": "2026-05-01T11:00:00.0000000", "timeZone": "UTC"},
            "location": {"displayName": ""},
            "body": {
                "contentType": "html",
                "content": "<html><body><b>Bold</b> and <i>italic</i> text</body></html>",
            },
            "lastModifiedDateTime": "2026-04-01T00:00:00.0000000Z",
            "isCancelled": False,
            "type": "singleInstance",
            "seriesMasterId": None,
        }
        ev = normalize_event(raw)
        assert "<" not in ev.body_text
        assert "Bold" in ev.body_text
        assert "italic" in ev.body_text

    def test_plain_text_body_unchanged(self):
        raw = {
            "id": "test-id-2",
            "subject": "Test",
            "start": {"dateTime": "2026-05-01T10:00:00.0000000", "timeZone": "UTC"},
            "end": {"dateTime": "2026-05-01T11:00:00.0000000", "timeZone": "UTC"},
            "location": {"displayName": ""},
            "body": {
                "contentType": "text",
                "content": "Plain text body",
            },
            "lastModifiedDateTime": "2026-04-01T00:00:00.0000000Z",
            "isCancelled": False,
            "type": "singleInstance",
            "seriesMasterId": None,
        }
        ev = normalize_event(raw)
        assert ev.body_text == "Plain text body"


class TestMissingOptionalLocation:
    def test_null_location_field(self):
        raw = {
            "id": "test-id-3",
            "subject": "No Location",
            "start": {"dateTime": "2026-05-01T10:00:00.0000000", "timeZone": "UTC"},
            "end": {"dateTime": "2026-05-01T11:00:00.0000000", "timeZone": "UTC"},
            "location": {"displayName": ""},
            "body": {"contentType": "text", "content": ""},
            "lastModifiedDateTime": "2026-04-01T00:00:00.0000000Z",
            "isCancelled": False,
            "type": "singleInstance",
            "seriesMasterId": None,
        }
        ev = normalize_event(raw)
        assert ev.location is None

    def test_absent_location_field(self):
        raw = {
            "id": "test-id-4",
            "subject": "No Location Key",
            "start": {"dateTime": "2026-05-01T10:00:00.0000000", "timeZone": "UTC"},
            "end": {"dateTime": "2026-05-01T11:00:00.0000000", "timeZone": "UTC"},
            "body": {"contentType": "text", "content": ""},
            "lastModifiedDateTime": "2026-04-01T00:00:00.0000000Z",
            "isCancelled": False,
            "type": "singleInstance",
            "seriesMasterId": None,
        }
        ev = normalize_event(raw)
        assert ev.location is None

    def test_second_event_empty_location(self):
        page = load_fixture("graph_calendarview_page.json")
        ev = normalize_event(page["value"][1])
        assert ev.location is None
