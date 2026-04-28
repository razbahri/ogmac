from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from ogmac.google import apply_action, fetch_target_events, find_orphan_by_instance_id
from ogmac.models import Action, ActionKind, SourceEvent, TargetEvent

FIXTURES = Path(__file__).parent.parent / "fixtures" / "google_events_list.json"

_CALENDAR_ID = "test-calendar@group.calendar.google.com"
_NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)
_FUTURE = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)

_FIXTURE_DATA = json.loads(FIXTURES.read_text())


def _make_service(list_response=None, insert_response=None):
    service = MagicMock()
    events = service.events.return_value
    list_req = events.list.return_value
    list_req.execute.return_value = list_response or {"items": []}
    insert_req = events.insert.return_value
    insert_req.execute.return_value = insert_response or {"id": "new_google_id_xyz"}
    update_req = events.update.return_value
    update_req.execute.return_value = {}
    delete_req = events.delete.return_value
    delete_req.execute.return_value = {}
    return service


def _fake_creds():
    return MagicMock()


def _source_event(**kwargs) -> SourceEvent:
    defaults = dict(
        outlook_id="outlook-id-001",
        instance_id="instance-001",
        subject="Team Standup",
        start_utc=datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
        end_utc=datetime(2026, 4, 29, 9, 15, tzinfo=timezone.utc),
        location="Zoom",
        body_text="Daily standup call.",
        last_modified=datetime(2026, 4, 27, 8, 0, tzinfo=timezone.utc),
        is_cancelled=False,
    )
    defaults.update(kwargs)
    return SourceEvent(**defaults)


def _target_event(**kwargs) -> TargetEvent:
    defaults = dict(
        google_id="google-evt-001",
        etag='"abc123"',
        instance_id="instance-001",
        last_synced_outlook_modified=datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return TargetEvent(**defaults)


class TestFetchTargetEventsSinglePage:
    def test_returns_target_events(self):
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service(list_response=_FIXTURE_DATA)
            mock_build.return_value = service

            results = fetch_target_events(_fake_creds(), _CALENDAR_ID, _NOW, _FUTURE)

        assert len(results) == 2
        assert results[0].google_id == "google_evt_aaa111"
        assert results[1].google_id == "google_evt_bbb222"

    def test_calls_list_with_correct_kwargs(self):
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service(list_response={"items": []})
            mock_build.return_value = service

            fetch_target_events(_fake_creds(), _CALENDAR_ID, _NOW, _FUTURE)

        service.events().list.assert_called_once_with(
            calendarId=_CALENDAR_ID,
            timeMin=_NOW.isoformat(),
            timeMax=_FUTURE.isoformat(),
            singleEvents=True,
            showDeleted=False,
            privateExtendedProperty="ogmac_owned=1",
            maxResults=2500,
        )

    def test_parses_extended_properties(self):
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service(list_response=_FIXTURE_DATA)
            mock_build.return_value = service

            results = fetch_target_events(_fake_creds(), _CALENDAR_ID, _NOW, _FUTURE)

        evt = results[0]
        assert evt.instance_id == "AAMkADEwNjQ5OWMxLTk3OTEtNGIyZi1iMGVlLTMwZjRmNThhNzI2ZABGAAAAAADrX"
        assert evt.last_synced_outlook_modified == datetime(2026, 4, 27, 9, 15, tzinfo=timezone.utc)
        assert evt.etag == '"3421234567890000"'

    def test_parses_second_event_correctly(self):
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service(list_response=_FIXTURE_DATA)
            mock_build.return_value = service

            results = fetch_target_events(_fake_creds(), _CALENDAR_ID, _NOW, _FUTURE)

        evt = results[1]
        assert evt.google_id == "google_evt_bbb222"
        assert evt.instance_id == "AAMkADEwNjQ5OWMxLTk3OTEtNGIyZi1iMGVlLTMwZjRmNThhNzI2ZABGAAAAAADrY"
        assert evt.last_synced_outlook_modified == datetime(2026, 4, 26, 16, 30, tzinfo=timezone.utc)


class TestFetchTargetEventsPagination:
    def test_follows_next_page_token(self):
        page1 = {
            "items": [_FIXTURE_DATA["items"][0]],
            "nextPageToken": "token-page2",
        }
        page2 = {
            "items": [_FIXTURE_DATA["items"][1]],
        }

        with patch("ogmac.google._build_service") as mock_build:
            service = MagicMock()
            events = service.events.return_value
            list_req = MagicMock()
            list_req.execute.side_effect = [page1, page2]
            events.list.return_value = list_req
            mock_build.return_value = service

            results = fetch_target_events(_fake_creds(), _CALENDAR_ID, _NOW, _FUTURE)

        assert len(results) == 2
        assert events.list.call_count == 2
        second_call_kwargs = events.list.call_args_list[1][1]
        assert second_call_kwargs["pageToken"] == "token-page2"

    def test_no_page_token_on_first_call(self):
        page1 = {"items": [_FIXTURE_DATA["items"][0]], "nextPageToken": "tok"}
        page2 = {"items": []}

        with patch("ogmac.google._build_service") as mock_build:
            service = MagicMock()
            events = service.events.return_value
            req = MagicMock()
            req.execute.side_effect = [page1, page2]
            events.list.return_value = req
            mock_build.return_value = service

            fetch_target_events(_fake_creds(), _CALENDAR_ID, _NOW, _FUTURE)

        first_call_kwargs = events.list.call_args_list[0][1]
        assert "pageToken" not in first_call_kwargs


class TestApplyActionCreate:
    def test_returns_new_google_id(self):
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service(insert_response={"id": "created-id-001"})
            mock_build.return_value = service

            action = Action(kind=ActionKind.CREATE, source=_source_event(), target=None)
            result = apply_action(_fake_creds(), _CALENDAR_ID, action)

        assert result == "created-id-001"

    def test_event_body_matches_spec(self):
        src = _source_event()
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service(insert_response={"id": "x"})
            mock_build.return_value = service

            action = Action(kind=ActionKind.CREATE, source=src, target=None)
            apply_action(_fake_creds(), _CALENDAR_ID, action)

        body = service.events().insert.call_args[1]["body"]
        assert body["summary"] == src.subject
        assert body["location"] == src.location
        assert body["description"] == src.body_text
        assert body["start"] == {"dateTime": src.start_utc.isoformat(), "timeZone": "UTC"}
        assert body["end"] == {"dateTime": src.end_utc.isoformat(), "timeZone": "UTC"}
        assert body["extendedProperties"]["private"]["ogmac_owned"] == "1"
        assert body["extendedProperties"]["private"]["ogmac_instance_id"] == src.instance_id
        assert body["extendedProperties"]["private"]["ogmac_source_modified"] == src.last_modified.isoformat()

    def test_no_attendees_in_body(self):
        src = _source_event()
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service(insert_response={"id": "x"})
            mock_build.return_value = service

            action = Action(kind=ActionKind.CREATE, source=src, target=None)
            apply_action(_fake_creds(), _CALENDAR_ID, action)

        body = service.events().insert.call_args[1]["body"]
        assert "attendees" not in body

    def test_calls_insert_with_calendar_id(self):
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service(insert_response={"id": "x"})
            mock_build.return_value = service

            action = Action(kind=ActionKind.CREATE, source=_source_event(), target=None)
            apply_action(_fake_creds(), _CALENDAR_ID, action)

        assert service.events().insert.call_args[1]["calendarId"] == _CALENDAR_ID


class TestApplyActionUpdate:
    def test_returns_same_google_id(self):
        tgt = _target_event(google_id="existing-google-id")
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service()
            mock_build.return_value = service

            action = Action(kind=ActionKind.UPDATE, source=_source_event(), target=tgt)
            result = apply_action(_fake_creds(), _CALENDAR_ID, action)

        assert result == "existing-google-id"

    def test_calls_update_with_correct_event_id(self):
        tgt = _target_event(google_id="existing-google-id")
        src = _source_event()
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service()
            mock_build.return_value = service

            action = Action(kind=ActionKind.UPDATE, source=src, target=tgt)
            apply_action(_fake_creds(), _CALENDAR_ID, action)

        call_kwargs = service.events().update.call_args[1]
        assert call_kwargs["calendarId"] == _CALENDAR_ID
        assert call_kwargs["eventId"] == "existing-google-id"

    def test_no_attendees_in_body(self):
        tgt = _target_event()
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service()
            mock_build.return_value = service

            action = Action(kind=ActionKind.UPDATE, source=_source_event(), target=tgt)
            apply_action(_fake_creds(), _CALENDAR_ID, action)

        body = service.events().update.call_args[1]["body"]
        assert "attendees" not in body


class TestApplyActionDelete:
    def test_returns_none(self):
        tgt = _target_event(google_id="to-delete-id")
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service()
            mock_build.return_value = service

            action = Action(kind=ActionKind.DELETE, source=None, target=tgt)
            result = apply_action(_fake_creds(), _CALENDAR_ID, action)

        assert result is None

    def test_calls_delete_with_correct_event_id(self):
        tgt = _target_event(google_id="to-delete-id")
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service()
            mock_build.return_value = service

            action = Action(kind=ActionKind.DELETE, source=None, target=tgt)
            apply_action(_fake_creds(), _CALENDAR_ID, action)

        call_kwargs = service.events().delete.call_args[1]
        assert call_kwargs["calendarId"] == _CALENDAR_ID
        assert call_kwargs["eventId"] == "to-delete-id"


class TestApplyActionSkip:
    def test_returns_none(self):
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service()
            mock_build.return_value = service

            action = Action(kind=ActionKind.SKIP, source=_source_event(), target=_target_event())
            result = apply_action(_fake_creds(), _CALENDAR_ID, action)

        assert result is None

    def test_makes_no_api_calls(self):
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service()
            mock_build.return_value = service

            action = Action(kind=ActionKind.SKIP, source=_source_event(), target=_target_event())
            apply_action(_fake_creds(), _CALENDAR_ID, action)

        service.events().insert.assert_not_called()
        service.events().update.assert_not_called()
        service.events().delete.assert_not_called()


class TestFindOrphanByInstanceId:
    def test_zero_results_returns_none(self):
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service(list_response={"items": []})
            mock_build.return_value = service

            result = find_orphan_by_instance_id(_fake_creds(), _CALENDAR_ID, "instance-x")

        assert result is None

    def test_one_result_returns_target_event(self):
        response = {"items": [_FIXTURE_DATA["items"][0]]}
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service(list_response=response)
            mock_build.return_value = service

            result = find_orphan_by_instance_id(_fake_creds(), _CALENDAR_ID, "instance-x")

        assert isinstance(result, TargetEvent)
        assert result.google_id == "google_evt_aaa111"

    def test_two_results_logs_warning_returns_first(self, caplog):
        response = {"items": _FIXTURE_DATA["items"]}
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service(list_response=response)
            mock_build.return_value = service

            with caplog.at_level(logging.WARNING, logger="ogmac.google"):
                result = find_orphan_by_instance_id(_fake_creds(), _CALENDAR_ID, "instance-dup")

        assert result.google_id == "google_evt_aaa111"
        assert any("2" in r.message for r in caplog.records if r.levelno == logging.WARNING)

    def test_query_uses_instance_id_filter(self):
        with patch("ogmac.google._build_service") as mock_build:
            service = _make_service(list_response={"items": []})
            mock_build.return_value = service

            find_orphan_by_instance_id(_fake_creds(), _CALENDAR_ID, "my-instance-id")

        call_kwargs = service.events().list.call_args[1]
        assert call_kwargs["privateExtendedProperty"] == "ogmac_instance_id=my-instance-id"
        assert call_kwargs["maxResults"] == 2
        assert call_kwargs["singleEvents"] is True
        assert call_kwargs["showDeleted"] is False


class TestRetry:
    def _make_http_error(self, status: int, retry_after: str | None = None) -> HttpError:
        resp = MagicMock()
        resp.status = status
        headers = {}
        if retry_after is not None:
            headers["Retry-After"] = retry_after
        resp.headers = headers
        return HttpError(resp=resp, content=b"error")

    def test_429_retries_then_succeeds(self):
        err = self._make_http_error(429)
        with patch("ogmac.google._build_service") as mock_build:
            service = MagicMock()
            events = service.events.return_value
            req = MagicMock()
            req.execute.side_effect = [err, {"items": []}]
            events.list.return_value = req
            mock_build.return_value = service

            with patch("ogmac.google.time.sleep") as mock_sleep:
                results = fetch_target_events(_fake_creds(), _CALENDAR_ID, _NOW, _FUTURE)

        assert results == []
        assert req.execute.call_count == 2
        mock_sleep.assert_called_once()

    def test_retry_after_header_used(self):
        err = self._make_http_error(429, retry_after="5")
        with patch("ogmac.google._build_service") as mock_build:
            service = MagicMock()
            events = service.events.return_value
            req = MagicMock()
            req.execute.side_effect = [err, {"items": []}]
            events.list.return_value = req
            mock_build.return_value = service

            with patch("ogmac.google.time.sleep") as mock_sleep:
                fetch_target_events(_fake_creds(), _CALENDAR_ID, _NOW, _FUTURE)

        mock_sleep.assert_called_once_with(5.0)

    def test_401_not_retried_raises(self):
        err = self._make_http_error(401)
        with patch("ogmac.google._build_service") as mock_build:
            service = MagicMock()
            events = service.events.return_value
            req = MagicMock()
            req.execute.side_effect = err
            events.list.return_value = req
            mock_build.return_value = service

            with pytest.raises(HttpError) as exc_info:
                fetch_target_events(_fake_creds(), _CALENDAR_ID, _NOW, _FUTURE)

        assert exc_info.value.resp.status == 401
        assert req.execute.call_count == 1
