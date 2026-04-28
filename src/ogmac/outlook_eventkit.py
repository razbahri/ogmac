from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from EventKit import (
    EKAuthorizationStatusAuthorized,
    EKAuthorizationStatusFullAccess,
    EKEntityTypeEvent,
    EKEventAvailabilityBusy,
    EKEventAvailabilityFree,
    EKEventAvailabilityTentative,
    EKEventAvailabilityUnavailable,
    EKEventStatusCanceled,
    EKEventStore,
    EKSourceTypeExchange,
)
from Foundation import NSDate

from ogmac.models import SourceEvent

log = logging.getLogger(__name__)

_NON_PRIMARY_TITLES = {"birthdays", "united states holidays", "holidays"}

_AVAILABILITY_MAP = {
    EKEventAvailabilityFree: "free",
    EKEventAvailabilityBusy: "busy",
    EKEventAvailabilityTentative: "tentative",
    EKEventAvailabilityUnavailable: "outOfOffice",
}


class EventKitAccessError(RuntimeError):
    pass


def _ensure_access(store: EKEventStore) -> None:
    status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)
    if status in (EKAuthorizationStatusAuthorized, EKAuthorizationStatusFullAccess):
        return

    granted = {"v": None}

    def cb(ok, err):
        granted["v"] = bool(ok)

    if hasattr(store, "requestFullAccessToEventsWithCompletion_"):
        store.requestFullAccessToEventsWithCompletion_(cb)
    else:
        store.requestAccessToEntityType_completion_(EKEntityTypeEvent, cb)

    deadline = time.time() + 30
    while granted["v"] is None and time.time() < deadline:
        time.sleep(0.1)

    if not granted["v"]:
        raise EventKitAccessError(
            "Calendar access denied. Grant access in System Settings > Privacy & Security > Calendars."
        )


def _select_calendars(store: EKEventStore, source_calendar: str):
    cals = store.calendarsForEntityType_(EKEntityTypeEvent)

    if source_calendar != "default":
        match = [c for c in cals if c.calendarIdentifier() == source_calendar]
        if not match:
            raise EventKitAccessError(f"No calendar with identifier '{source_calendar}' found.")
        return match

    exchange_cals = [
        c for c in cals
        if c.source() is not None and c.source().sourceType() == EKSourceTypeExchange
    ]
    primary = [c for c in exchange_cals if c.title().lower() not in _NON_PRIMARY_TITLES]
    if not primary:
        raise EventKitAccessError("No Exchange primary calendar found.")
    return primary[:1]


def _to_utc(nsdate) -> datetime:
    return datetime.fromtimestamp(nsdate.timeIntervalSince1970(), tz=timezone.utc)


def _ns_from_utc(dt: datetime):
    return NSDate.dateWithTimeIntervalSince1970_(dt.timestamp())


def _normalize(event) -> SourceEvent:
    outlook_id = str(event.eventIdentifier())
    start_dt = _to_utc(event.startDate())
    end_dt = _to_utc(event.endDate())
    instance_id = f"{outlook_id}|{int(start_dt.timestamp())}"
    last_mod = event.lastModifiedDate() or event.creationDate() or event.startDate()
    availability = _AVAILABILITY_MAP.get(event.availability(), "busy")
    return SourceEvent(
        outlook_id=outlook_id,
        instance_id=instance_id,
        subject=event.title() or "",
        start_utc=start_dt,
        end_utc=end_dt,
        location=event.location() or None,
        body_text=event.notes() or "",
        last_modified=_to_utc(last_mod),
        is_cancelled=event.status() == EKEventStatusCanceled,
        availability=availability,
        is_all_day=bool(event.isAllDay()),
    )


def fetch_source_events(
    token: str,
    source_calendar: str,
    start: datetime,
    end: datetime,
) -> list[SourceEvent]:
    """Read events from macOS EventKit. `token` is unused — kept for signature parity with the Graph backend."""
    del token
    store = EKEventStore.alloc().init()
    _ensure_access(store)
    cals = _select_calendars(store, source_calendar)
    log.info("eventkit.calendars selected=%s", [c.title() for c in cals])
    pred = store.predicateForEventsWithStartDate_endDate_calendars_(
        _ns_from_utc(start), _ns_from_utc(end), cals
    )
    events = store.eventsMatchingPredicate_(pred) or []
    return [_normalize(e) for e in events]
