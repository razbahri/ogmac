from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ogmac.models import Action, ActionKind, TargetEvent

log = logging.getLogger(__name__)

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0
_BACKOFF_CAP = 10.0


def _execute_with_retry(request: Any) -> Any:
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return request.execute()
        except HttpError as exc:
            status = exc.resp.status
            if status not in _RETRY_STATUSES or attempt == _MAX_RETRIES:
                raise
            retry_after = exc.resp.headers.get("Retry-After")
            if retry_after is not None:
                delay = float(retry_after)
            else:
                delay = min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_CAP)
            log.warning("google api %d on attempt %d, retrying in %.1fs", status, attempt + 1, delay)
            time.sleep(delay)


def _build_service(credentials: Any) -> Any:
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _parse_target_event(item: dict) -> TargetEvent:
    private = item.get("extendedProperties", {}).get("private", {})
    raw_modified = private.get("ogmac_source_modified", "")
    last_synced = datetime.fromisoformat(raw_modified).replace(tzinfo=timezone.utc) \
        if raw_modified else datetime.min.replace(tzinfo=timezone.utc)
    return TargetEvent(
        google_id=item["id"],
        etag=item.get("etag", ""),
        instance_id=private.get("ogmac_instance_id", ""),
        last_synced_outlook_modified=last_synced,
    )


def fetch_target_events(
    credentials: Any,
    calendar_id: str,
    start: datetime,
    end: datetime,
) -> list[TargetEvent]:
    service = _build_service(credentials)
    events_resource = service.events()
    results: list[TargetEvent] = []
    page_token: str | None = None

    while True:
        kwargs: dict[str, Any] = {
            "calendarId": calendar_id,
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "singleEvents": True,
            "showDeleted": False,
            "privateExtendedProperty": "ogmac_owned=1",
            "maxResults": 2500,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = _execute_with_retry(events_resource.list(**kwargs))
        for item in response.get("items", []):
            results.append(_parse_target_event(item))

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return results


def apply_action(
    credentials: Any,
    calendar_id: str,
    action: Action,
) -> str | None:
    if action.kind is ActionKind.SKIP:
        return None

    service = _build_service(credentials)
    events_resource = service.events()

    if action.kind is ActionKind.DELETE:
        _execute_with_retry(
            events_resource.delete(
                calendarId=calendar_id,
                eventId=action.target.google_id,
            )
        )
        return None

    src = action.source
    if src.is_all_day:
        local_tz = datetime.now().astimezone().tzinfo
        start_date = src.start_utc.astimezone(local_tz).date()
        end_date = src.end_utc.astimezone(local_tz).date() + timedelta(days=1)
        start_block = {"date": start_date.isoformat()}
        end_block = {"date": end_date.isoformat()}
    else:
        start_block = {"dateTime": src.start_utc.isoformat(), "timeZone": "UTC"}
        end_block = {"dateTime": src.end_utc.isoformat(), "timeZone": "UTC"}

    event_body = {
        "summary": src.subject,
        "location": src.location,
        "description": src.body_text,
        "start": start_block,
        "end": end_block,
        "transparency": "transparent" if src.availability == "free" else "opaque",
        "extendedProperties": {"private": {
            "ogmac_owned": "1",
            "ogmac_instance_id": src.instance_id,
            "ogmac_source_modified": src.last_modified.isoformat(),
        }},
    }
    if src.availability == "outOfOffice":
        event_body["eventType"] = "outOfOffice"

    if action.kind is ActionKind.CREATE:
        result = _execute_with_retry(
            events_resource.insert(calendarId=calendar_id, body=event_body)
        )
        return result["id"]

    if action.kind is ActionKind.UPDATE:
        _execute_with_retry(
            events_resource.update(
                calendarId=calendar_id,
                eventId=action.target.google_id,
                body=event_body,
            )
        )
        return action.target.google_id

    return None


def find_orphan_by_instance_id(
    credentials: Any,
    calendar_id: str,
    instance_id: str,
) -> TargetEvent | None:
    service = _build_service(credentials)
    response = _execute_with_retry(
        service.events().list(
            calendarId=calendar_id,
            privateExtendedProperty=f"ogmac_instance_id={instance_id}",
            singleEvents=True,
            showDeleted=False,
            maxResults=2,
        )
    )
    items = response.get("items", [])
    if not items:
        return None
    if len(items) >= 2:
        log.warning(
            "find_orphan_by_instance_id: found %d events for instance_id=%s, using first",
            len(items),
            instance_id,
        )
    return _parse_target_event(items[0])
