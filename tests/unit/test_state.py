from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ogmac.state import State


def utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


@pytest.fixture
def state(tmp_path):
    s = State(tmp_path / "state.db")
    yield s
    s.close()


# ── schema idempotency ─────────────────────────────────────────────────────

def test_schema_idempotent(tmp_path):
    db = tmp_path / "state.db"
    s1 = State(db)
    s1.close()
    s2 = State(db)
    s2.close()


# ── event_map round-trips ──────────────────────────────────────────────────

def test_put_and_get_mapping(state):
    lsm = utc("2026-04-28T10:00:00")
    state.put_mapping("outlook-1", "google-1", lsm)
    m = state.get_mapping("outlook-1")
    assert m is not None
    assert m.instance_id == "outlook-1"
    assert m.google_id == "google-1"
    assert m.last_source_modified == lsm


def test_get_mapping_missing(state):
    assert state.get_mapping("nonexistent") is None


def test_put_mapping_updates_existing(state):
    lsm1 = utc("2026-04-28T10:00:00")
    lsm2 = utc("2026-04-28T11:00:00")
    state.put_mapping("outlook-1", "google-1", lsm1)
    created_at = state.get_mapping("outlook-1").created_at
    state.put_mapping("outlook-1", "google-2", lsm2)
    m = state.get_mapping("outlook-1")
    assert m.google_id == "google-2"
    assert m.last_source_modified == lsm2
    assert m.created_at == created_at


def test_delete_mapping(state):
    state.put_mapping("outlook-1", "google-1", utc("2026-04-28T10:00:00"))
    state.delete_mapping("outlook-1")
    assert state.get_mapping("outlook-1") is None


def test_delete_mapping_nonexistent_is_noop(state):
    state.delete_mapping("does-not-exist")


def test_all_mappings_empty(state):
    assert state.all_mappings() == []


def test_all_mappings_multiple(state):
    state.put_mapping("a", "ga", utc("2026-04-28T10:00:00"))
    state.put_mapping("b", "gb", utc("2026-04-28T11:00:00"))
    result = {m.instance_id: m.google_id for m in state.all_mappings()}
    assert result == {"a": "ga", "b": "gb"}


def test_mapping_datetimes_have_utc_tzinfo(state):
    state.put_mapping("x", "gx", utc("2026-04-28T12:00:00"))
    m = state.get_mapping("x")
    assert m.last_source_modified.tzinfo is not None
    assert m.created_at.tzinfo is not None
    assert m.updated_at.tzinfo is not None


# ── run_state round-trips ──────────────────────────────────────────────────

def test_set_and_get_run_state(state):
    state.set_run_state("mykey", "myval")
    assert state.get_run_state("mykey") == "myval"


def test_get_run_state_default(state):
    assert state.get_run_state("missing") is None
    assert state.get_run_state("missing", "fallback") == "fallback"


def test_set_run_state_overwrites(state):
    state.set_run_state("k", "v1")
    state.set_run_state("k", "v2")
    assert state.get_run_state("k") == "v2"


def test_delete_run_state(state):
    state.set_run_state("k", "v")
    state.delete_run_state("k")
    assert state.get_run_state("k") is None


def test_delete_run_state_nonexistent_is_noop(state):
    state.delete_run_state("no-such-key")


# ── failure counter ────────────────────────────────────────────────────────

def test_consecutive_failures_starts_at_zero(state):
    assert state.consecutive_failures == 0


def test_increment_failures(state):
    assert state.increment_failures() == 1
    assert state.increment_failures() == 2
    assert state.consecutive_failures == 2


def test_reset_failures(state):
    state.increment_failures()
    state.increment_failures()
    state.reset_failures()
    assert state.consecutive_failures == 0


# ── disable / enable ───────────────────────────────────────────────────────

def test_not_disabled_by_default(state):
    assert state.is_disabled is False


def test_disable_and_enable(state):
    state.disable("5 consecutive failures: TimeoutError")
    assert state.is_disabled is True
    state.enable()
    assert state.is_disabled is False


def test_enable_clears_reason(state):
    state.disable("some reason")
    state.enable()
    assert state.get_run_state("disable_reason") is None


# ── wipe operations ────────────────────────────────────────────────────────

def test_wipe_event_map(state):
    state.put_mapping("a", "ga", utc("2026-04-28T10:00:00"))
    state.put_mapping("b", "gb", utc("2026-04-28T10:00:00"))
    state.wipe_event_map()
    assert state.all_mappings() == []


def test_wipe_run_state(state):
    state.set_run_state("k1", "v1")
    state.disable("reason")
    state.wipe_run_state()
    assert state.get_run_state("k1") is None
    assert state.is_disabled is False
    assert state.consecutive_failures == 0


def test_wipe_event_map_does_not_affect_run_state(state):
    state.set_run_state("foo", "bar")
    state.put_mapping("a", "ga", utc("2026-04-28T10:00:00"))
    state.wipe_event_map()
    assert state.get_run_state("foo") == "bar"


def test_wipe_run_state_does_not_affect_event_map(state):
    state.put_mapping("a", "ga", utc("2026-04-28T10:00:00"))
    state.set_run_state("foo", "bar")
    state.wipe_run_state()
    assert len(state.all_mappings()) == 1
