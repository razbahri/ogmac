from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SourceEvent:
    outlook_id: str
    instance_id: str
    subject: str
    start_utc: datetime
    end_utc: datetime
    location: str | None
    body_text: str
    last_modified: datetime
    is_cancelled: bool
    availability: str = "busy"
    is_all_day: bool = False


@dataclass(frozen=True)
class TargetEvent:
    google_id: str
    etag: str
    instance_id: str
    last_synced_outlook_modified: datetime


class ActionKind(enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SKIP = "SKIP"


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    source: SourceEvent | None
    target: TargetEvent | None
