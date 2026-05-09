from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ogmac.cli import _compute_sync_window

# Fixed test timezone: IDT (UTC+3). Avoids depending on the runner's local TZ.
IDT = timezone(timedelta(hours=3))


def test_window_aligns_to_local_midnight():
    # 9 May 14:23:45 UTC == 9 May 17:23:45 IDT.
    # Today (in IDT) midnight = 9 May 00:00 IDT = 8 May 21:00 UTC.
    # past=1: start = 8 May 00:00 IDT = 7 May 21:00 UTC.
    # future=30: end = 9 May + 31d at 00:00 IDT = 9 Jun 00:00 IDT = 8 Jun 21:00 UTC.
    now = datetime(2026, 5, 9, 14, 23, 45, tzinfo=timezone.utc)
    start, end = _compute_sync_window(now, past_days=1, future_days=30, tz=IDT)
    assert start == datetime(2026, 5, 7, 21, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 6, 8, 21, 0, tzinfo=timezone.utc)


def test_window_invariant_within_a_local_day():
    # Two runs at different times of the same IDT day produce the same window.
    morning = datetime(2026, 5, 9, 0, 5, 0, tzinfo=IDT)
    evening = datetime(2026, 5, 9, 23, 55, 0, tzinfo=IDT)
    s1, e1 = _compute_sync_window(morning, past_days=1, future_days=30, tz=IDT)
    s2, e2 = _compute_sync_window(evening, past_days=1, future_days=30, tz=IDT)
    assert s1 == s2
    assert e1 == e2


def test_window_zero_days_is_one_day():
    # past=0, future=0 → window is exactly today (24h, exclusive end).
    now = datetime(2026, 5, 9, 14, 23, 45, tzinfo=timezone.utc)
    start, end = _compute_sync_window(now, past_days=0, future_days=0, tz=IDT)
    assert end - start == timedelta(days=1)


def test_window_returns_utc_datetimes():
    now = datetime(2026, 5, 9, 14, 23, 45, tzinfo=timezone.utc)
    start, end = _compute_sync_window(now, past_days=1, future_days=30, tz=IDT)
    assert start.tzinfo == timezone.utc
    assert end.tzinfo == timezone.utc


def test_window_end_is_exclusive():
    # past=0, future=0 → today only. end is the FIRST instant of tomorrow,
    # not the last instant of today.
    now = datetime(2026, 5, 9, 12, 0, 0, tzinfo=IDT)
    start, end = _compute_sync_window(now, past_days=0, future_days=0, tz=IDT)
    assert start.astimezone(IDT) == datetime(2026, 5, 9, 0, 0, 0, tzinfo=IDT)
    assert end.astimezone(IDT) == datetime(2026, 5, 10, 0, 0, 0, tzinfo=IDT)
