from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from html.parser import HTMLParser

import httpx

from ogmac.models import SourceEvent

log = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_SELECT = "id,subject,start,end,location,body,lastModifiedDateTime,isCancelled,type,seriesMasterId"
_TOP = 250
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BASE_BACKOFF = 1.0
_MAX_BACKOFF = 10.0


class GraphError(Exception):
    pass


class GraphAuthError(GraphError):
    pass


class _TextStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def _strip_html(html: str) -> str:
    stripper = _TextStripper()
    stripper.feed(html)
    return stripper.get_text()


def _parse_utc(dt_str: str) -> datetime:
    dt = datetime.fromisoformat(dt_str.rstrip("Z").replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_event(payload: dict) -> SourceEvent:
    series_master_id = payload.get("seriesMasterId")
    outlook_id = series_master_id if series_master_id else payload["id"]
    instance_id = payload["id"]

    subject = payload.get("subject") or ""

    start_info = payload.get("start", {})
    end_info = payload.get("end", {})
    start_utc = _parse_utc(start_info["dateTime"])
    end_utc = _parse_utc(end_info["dateTime"])

    loc_display = (payload.get("location") or {}).get("displayName") or None
    location = loc_display if loc_display else None

    body_info = payload.get("body", {})
    raw_body = body_info.get("content", "")
    if body_info.get("contentType", "").lower() == "html":
        body_text = _strip_html(raw_body)
    else:
        body_text = raw_body

    last_modified = _parse_utc(payload["lastModifiedDateTime"])
    is_cancelled = bool(payload.get("isCancelled", False))

    return SourceEvent(
        outlook_id=outlook_id,
        instance_id=instance_id,
        subject=subject,
        start_utc=start_utc,
        end_utc=end_utc,
        location=location,
        body_text=body_text,
        last_modified=last_modified,
        is_cancelled=is_cancelled,
    )


def _calendar_view_url(source_calendar: str) -> str:
    if source_calendar == "default":
        return f"{_GRAPH_BASE}/me/calendarView"
    return f"{_GRAPH_BASE}/me/calendars/{source_calendar}/calendarView"


def _get_with_retry(client: httpx.Client, url: str, params: dict | None, headers: dict) -> dict:
    for attempt in range(_MAX_RETRIES + 1):
        resp = client.get(url, params=params, headers=headers)

        if resp.status_code == 401:
            raise GraphAuthError(f"Graph returned 401; re-run 'ogmac login': {resp.text}")

        if resp.status_code not in _RETRY_STATUSES:
            resp.raise_for_status()
            return resp.json()

        if attempt == _MAX_RETRIES:
            resp.raise_for_status()

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after is not None else min(_BASE_BACKOFF * (2 ** attempt), _MAX_BACKOFF)
        else:
            wait = min(_BASE_BACKOFF * (2 ** attempt), _MAX_BACKOFF)

        log.warning("Graph %s on attempt %d; retrying in %.1fs", resp.status_code, attempt + 1, wait)
        time.sleep(wait)

    raise GraphError("Unreachable")


def fetch_source_events(
    token: str,
    source_calendar: str,
    start: datetime,
    end: datetime,
) -> list[SourceEvent]:
    url = _calendar_view_url(source_calendar)
    params: dict = {
        "startDateTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%S"),
        "$top": str(_TOP),
        "$select": _SELECT,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Prefer": 'outlook.timezone="UTC"',
    }

    events: list[SourceEvent] = []
    with httpx.Client(timeout=30.0) as client:
        while True:
            data = _get_with_retry(client, url, params, headers)
            for raw in data.get("value", []):
                events.append(normalize_event(raw))

            next_link = data.get("@odata.nextLink")
            if not next_link:
                break
            url = next_link
            params = {}

    log.info("outlook.fetch count=%d", len(events))
    return events
