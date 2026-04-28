"""Probe EventKit: request calendar access, list sources + calendars + recent events."""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone

from EventKit import (
    EKAuthorizationStatusAuthorized,
    EKAuthorizationStatusFullAccess,
    EKEntityTypeEvent,
    EKEventStore,
)
from Foundation import NSDate


def request_access(store: EKEventStore) -> bool:
    granted = {"v": None}

    def cb(ok: bool, err) -> None:
        granted["v"] = bool(ok)
        if err is not None:
            print(f"access error: {err}", file=sys.stderr)

    if hasattr(store, "requestFullAccessToEventsWithCompletion_"):
        store.requestFullAccessToEventsWithCompletion_(cb)
    else:
        store.requestAccessToEntityType_completion_(EKEntityTypeEvent, cb)

    deadline = time.time() + 30
    while granted["v"] is None and time.time() < deadline:
        time.sleep(0.1)
    return bool(granted["v"])


def main() -> int:
    store = EKEventStore.alloc().init()

    status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)
    print(f"initial authorization status: {status}")

    if status not in (EKAuthorizationStatusAuthorized, EKAuthorizationStatusFullAccess):
        print("requesting access...")
        if not request_access(store):
            print("ACCESS DENIED")
            return 2
        print("granted")

    print("\n=== sources ===")
    for s in store.sources():
        print(f"  {s.title()}  type={s.sourceType()}  id={s.sourceIdentifier()}")

    print("\n=== calendars ===")
    cals = store.calendarsForEntityType_(EKEntityTypeEvent)
    for c in cals:
        src = c.source()
        print(f"  {c.title():40s}  source={src.title() if src else '?':20s}  id={c.calendarIdentifier()}")

    work_cals = [c for c in cals if c.source() and "exchange" in c.source().title().lower()]
    if not work_cals:
        work_cals = [c for c in cals if c.source() and c.source().sourceType() == 2]
    if not work_cals:
        work_cals = [c for c in cals if c.title().lower() in ("calendar", "work")]

    print(f"\n=== work calendars detected: {[c.title() for c in work_cals]} ===")

    if work_cals:
        now = datetime.now(timezone.utc)
        start = NSDate.dateWithTimeIntervalSince1970_((now - timedelta(days=1)).timestamp())
        end = NSDate.dateWithTimeIntervalSince1970_((now + timedelta(days=7)).timestamp())
        pred = store.predicateForEventsWithStartDate_endDate_calendars_(start, end, work_cals)
        events = store.eventsMatchingPredicate_(pred) or []
        print(f"\n=== events in next 7d (work cals only): {len(events)} ===")
        for e in events[:20]:
            print(f"  {e.startDate()}  {e.title()}  loc={e.location() or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
