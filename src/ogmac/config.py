from __future__ import annotations

import warnings
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator


class ConfigError(Exception):
    pass


class OutlookConfig(BaseModel):
    account: str
    source_calendar: str = "default"
    read_method: Literal["apple_calendar", "microsoft_graph"] = "apple_calendar"


class GoogleConfig(BaseModel):
    account: str
    client_secret_path: Path
    target_calendar_id: str

    @field_validator("client_secret_path", mode="before")
    @classmethod
    def expand_path(cls, v: object) -> Path:
        return Path(str(v)).expanduser()


class SyncConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    window_past_days: int = 1
    window_future_days: int = 30


class PrivacyConfig(BaseModel):
    copy_subject: bool = True
    copy_location: bool = True
    copy_body: bool = True
    # copy_attendees is permanently locked to False; the validator below enforces
    # this so that a misconfigured YAML cannot accidentally enable attendee copying.
    copy_attendees: bool = False

    @field_validator("copy_attendees")
    @classmethod
    def attendees_must_be_false(cls, v: bool) -> bool:
        if v is True:
            raise ValueError(
                "copy_attendees must be false; attendee syncing is not supported"
            )
        return v


class FailureConfig(BaseModel):
    max_consecutive_before_disable: int = 5
    notify_on_failure: bool = True


class Config(BaseModel):
    outlook: OutlookConfig
    google: GoogleConfig
    sync: SyncConfig = SyncConfig()
    privacy: PrivacyConfig = PrivacyConfig()
    failure: FailureConfig = FailureConfig()

    @classmethod
    def load(cls, path: Path) -> "Config":
        try:
            raw = path.read_text()
        except FileNotFoundError:
            raise ConfigError(f"Config file not found: {path}")
        data = yaml.safe_load(raw)
        if isinstance(data.get("sync"), dict) and "interval_seconds" in data["sync"]:
            warnings.warn(
                "sync.interval_seconds is deprecated and has no effect; "
                "the sync interval is controlled by the launchd plist.",
                DeprecationWarning,
                stacklevel=2,
            )
        return cls.model_validate(data)

    @classmethod
    def default_path(cls) -> Path:
        return Path.home() / ".config" / "ogmac" / "config.yaml"
