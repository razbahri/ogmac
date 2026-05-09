from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Mapping:
    instance_id: str
    google_id: str
    last_source_modified: datetime
    created_at: datetime
    updated_at: datetime


_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS event_map (
    instance_id          TEXT PRIMARY KEY,
    google_id            TEXT NOT NULL,
    last_source_modified TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_google_id ON event_map(google_id);

CREATE TABLE IF NOT EXISTS run_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_KEY_FAILURES = "consecutive_failures"
_KEY_DISABLED = "disabled"
_KEY_DISABLE_REASON = "disable_reason"
_KEY_PAUSED = "paused"


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class State:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ── event_map ──────────────────────────────────────────────────────────

    def get_mapping(self, instance_id: str) -> Mapping | None:
        row = self._conn.execute(
            "SELECT instance_id, google_id, last_source_modified, created_at, updated_at "
            "FROM event_map WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()
        if row is None:
            return None
        return Mapping(
            instance_id=row[0],
            google_id=row[1],
            last_source_modified=_from_iso(row[2]),
            created_at=_from_iso(row[3]),
            updated_at=_from_iso(row[4]),
        )

    def put_mapping(
        self,
        instance_id: str,
        google_id: str,
        last_source_modified: datetime,
    ) -> None:
        now = _to_iso(_utcnow())
        lsm = _to_iso(last_source_modified)
        existing = self._conn.execute(
            "SELECT created_at FROM event_map WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()
        if existing is None:
            self._conn.execute(
                "INSERT INTO event_map (instance_id, google_id, last_source_modified, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (instance_id, google_id, lsm, now, now),
            )
        else:
            self._conn.execute(
                "UPDATE event_map SET google_id = ?, last_source_modified = ?, updated_at = ? "
                "WHERE instance_id = ?",
                (google_id, lsm, now, instance_id),
            )
        self._conn.commit()

    def delete_mapping(self, instance_id: str) -> None:
        self._conn.execute(
            "DELETE FROM event_map WHERE instance_id = ?", (instance_id,)
        )
        self._conn.commit()

    def all_mappings(self) -> list[Mapping]:
        rows = self._conn.execute(
            "SELECT instance_id, google_id, last_source_modified, created_at, updated_at FROM event_map"
        ).fetchall()
        return [
            Mapping(
                instance_id=r[0],
                google_id=r[1],
                last_source_modified=_from_iso(r[2]),
                created_at=_from_iso(r[3]),
                updated_at=_from_iso(r[4]),
            )
            for r in rows
        ]

    # ── run_state ──────────────────────────────────────────────────────────

    def get_run_state(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM run_state WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row is not None else default

    def set_run_state(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO run_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def delete_run_state(self, key: str) -> None:
        self._conn.execute("DELETE FROM run_state WHERE key = ?", (key,))
        self._conn.commit()

    # ── convenience ────────────────────────────────────────────────────────

    @property
    def consecutive_failures(self) -> int:
        raw = self.get_run_state(_KEY_FAILURES, "0")
        return int(raw)

    def increment_failures(self) -> int:
        new = self.consecutive_failures + 1
        self.set_run_state(_KEY_FAILURES, str(new))
        return new

    def reset_failures(self) -> None:
        self.set_run_state(_KEY_FAILURES, "0")

    @property
    def is_disabled(self) -> bool:
        return self.get_run_state(_KEY_DISABLED) == "1"

    def disable(self, reason: str) -> None:
        self.set_run_state(_KEY_DISABLED, "1")
        self.set_run_state(_KEY_DISABLE_REASON, reason)

    def enable(self) -> None:
        self.delete_run_state(_KEY_DISABLED)
        self.delete_run_state(_KEY_DISABLE_REASON)

    @property
    def is_paused(self) -> bool:
        return self.get_run_state(_KEY_PAUSED) == "1"

    def pause(self) -> None:
        self.set_run_state(_KEY_PAUSED, "1")

    def unpause(self) -> None:
        self.delete_run_state(_KEY_PAUSED)

    # ── wipe ───────────────────────────────────────────────────────────────

    def wipe_event_map(self) -> None:
        self._conn.execute("DELETE FROM event_map")
        self._conn.commit()

    def wipe_run_state(self) -> None:
        self._conn.execute("DELETE FROM run_state")
        self._conn.commit()
