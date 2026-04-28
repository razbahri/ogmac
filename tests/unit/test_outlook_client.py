from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ogmac.outlook import GraphAuthError, fetch_source_events

FIXTURES = Path(__file__).parent.parent / "fixtures"

START = datetime(2026, 4, 27, 0, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
TOKEN = "test-bearer-token"

_BASE_URL = "https://graph.microsoft.com/v1.0"
_DEFAULT_URL = f"{_BASE_URL}/me/calendarView"
_SPECIFIC_URL = f"{_BASE_URL}/me/calendars/cal-id-123/calendarView"


def _page(events: list, next_link: str | None = None) -> dict:
    return {"value": events, "@odata.nextLink": next_link}


def _single_event(eid: str = "EVT001") -> dict:
    return {
        "id": eid,
        "subject": "Test Event",
        "start": {"dateTime": "2026-05-01T10:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-05-01T11:00:00.0000000", "timeZone": "UTC"},
        "location": {"displayName": ""},
        "body": {"contentType": "text", "content": "body"},
        "lastModifiedDateTime": "2026-04-20T10:00:00.0000000Z",
        "isCancelled": False,
        "type": "singleInstance",
        "seriesMasterId": None,
    }


class TestSinglePage:
    def test_returns_events_from_single_page(self, httpx_mock):
        page = _page([_single_event("E1"), _single_event("E2")])
        httpx_mock.add_response(json=page)

        result = fetch_source_events(TOKEN, "default", START, END)

        assert len(result) == 2
        assert result[0].instance_id == "E1"
        assert result[1].instance_id == "E2"

    def test_no_next_link_stops_pagination(self, httpx_mock):
        httpx_mock.add_response(json=_page([_single_event()]))

        result = fetch_source_events(TOKEN, "default", START, END)
        assert len(result) == 1


class TestPagination:
    def test_two_pages_concatenated(self, httpx_mock):
        next_url = f"{_DEFAULT_URL}?%24skiptoken=abc"
        page1 = _page([_single_event("E1")], next_link=next_url)
        page2 = _page([_single_event("E2")])

        httpx_mock.add_response(json=page1)
        httpx_mock.add_response(json=page2)

        result = fetch_source_events(TOKEN, "default", START, END)
        assert len(result) == 2
        assert result[0].instance_id == "E1"
        assert result[1].instance_id == "E2"


class TestRetry:
    def test_429_once_then_200(self, httpx_mock):
        httpx_mock.add_response(
            status_code=429,
            headers={"Retry-After": "0"},
            json={"error": {"code": "TooManyRequests"}},
        )
        httpx_mock.add_response(json=_page([_single_event()]))

        result = fetch_source_events(TOKEN, "default", START, END)
        assert len(result) == 1

    def test_503_once_then_200(self, httpx_mock):
        httpx_mock.add_response(
            status_code=503,
            json={"error": {"code": "ServiceUnavailable"}},
        )
        httpx_mock.add_response(json=_page([_single_event()]))

        result = fetch_source_events(TOKEN, "default", START, END)
        assert len(result) == 1


class TestAuthFailure:
    def test_401_raises_graph_auth_error(self, httpx_mock):
        httpx_mock.add_response(status_code=401, text="Unauthorized")

        with pytest.raises(GraphAuthError):
            fetch_source_events(TOKEN, "default", START, END)

    def test_401_is_not_retried(self, httpx_mock):
        httpx_mock.add_response(status_code=401, text="Unauthorized")

        with pytest.raises(GraphAuthError):
            fetch_source_events(TOKEN, "default", START, END)

        requests = httpx_mock.get_requests()
        assert len(requests) == 1


class TestHeaders:
    def test_authorization_header(self, httpx_mock):
        httpx_mock.add_response(json=_page([]))

        fetch_source_events(TOKEN, "default", START, END)

        req = httpx_mock.get_requests()[0]
        assert req.headers["Authorization"] == f"Bearer {TOKEN}"

    def test_prefer_utc_header(self, httpx_mock):
        httpx_mock.add_response(json=_page([]))

        fetch_source_events(TOKEN, "default", START, END)

        req = httpx_mock.get_requests()[0]
        assert req.headers["Prefer"] == 'outlook.timezone="UTC"'


class TestUrlRouting:
    def test_default_calendar_uses_me_calendarview(self, httpx_mock):
        httpx_mock.add_response(json=_page([]))

        fetch_source_events(TOKEN, "default", START, END)

        req = httpx_mock.get_requests()[0]
        assert str(req.url).startswith(_DEFAULT_URL)

    def test_specific_calendar_uses_calendars_path(self, httpx_mock):
        httpx_mock.add_response(json=_page([]))

        fetch_source_events(TOKEN, "cal-id-123", START, END)

        req = httpx_mock.get_requests()[0]
        assert str(req.url).startswith(_SPECIFIC_URL)
