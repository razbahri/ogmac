# ogmac — Outlook → Google Calendar Sync for macOS

**Status:** design approved 2026-04-28
**Inspired by:** [OutlookGoogleCalendarSync](https://github.com/phw198/OutlookGoogleCalendarSync) (Windows)

## Goal

A macOS-native, locally-running, headless syncer that copies events from a work Outlook calendar (Microsoft 365 / Exchange Online) into a dedicated personal Google Calendar. One-way, every 15 minutes, via `launchd`. No cloud middleman, no server component, single-user.

## Why this exists

[OutlookGoogleCalendarSync](https://github.com/phw198/OutlookGoogleCalendarSync) on Windows relies on the Outlook desktop client's COM Interop surface, which does not exist on macOS. Cloud-hosted alternatives (CalendarBridge, etc.) require sending work calendar data through a third party, which is undesirable. The available local Mac alternatives either require classic Outlook for Mac (the New Outlook UI has minimal AppleScript surface) or are unmaintained. Therefore: build a small, durable Python tool.

## Locked-in decisions

| # | Decision |
|---|---|
| Direction | Outlook → Google, **one-way only** |
| Outlook backend | Microsoft Graph API, delegated OAuth, public Graph CLI client ID `14d82eec-204b-4c2f-b7e8-296a70dab67e` |
| UI surface | Headless, `launchd`-driven |
| Privacy | Copy: title, time, location, body. **Strip:** attendees |
| Calendar mapping | Default Outlook calendar → one dedicated Google calendar ("Work (synced)") |
| Sync window | Past 1 day, future 30 days |
| Drift handling (deletes) | Outlook delete → Google delete |
| Drift handling (manual edits in Google) | Overwrite on next change in Outlook |
| Recurring events | Expanded to individual occurrences (no RRULE in Google) |
| Cadence | 15 minutes (`StartInterval=900`) |
| Failure handling | Log + native notification + auto-disable after 5 consecutive failures |

---

## §1. Architecture

### Component diagram

```
                        ┌──────────────────────────────┐
                        │  launchd (every 15 min)      │
                        │  com.ogmac.sync.plist        │
                        └──────────────┬───────────────┘
                                       │ exec
                                       ▼
                        ┌──────────────────────────────┐
                        │  ogmac (Python entry point)  │
                        │  python -m ogmac.cli sync    │
                        └──────┬─────────┬─────────┬───┘
                               │         │         │
            ┌──────────────────┘         │         └──────────────────┐
            ▼                            ▼                            ▼
   ┌─────────────────┐        ┌─────────────────┐          ┌─────────────────┐
   │  outlook.py     │        │  reconciler.py  │          │  google.py      │
   │  Graph client   │        │  diff + apply   │          │  Calendar v3    │
   │  + expansion    │        │                 │          │  client         │
   └────────┬────────┘        └────────┬────────┘          └────────┬────────┘
            │                          │                            │
            │                          ▼                            │
            │                 ┌─────────────────┐                   │
            │                 │  state.py       │                   │
            │                 │  SQLite mapping │                   │
            │                 └─────────────────┘                   │
            │                                                       │
            └──────────  auth.py (msal + keyring) ──────────────────┘
                                       │
                                       ▼
                          ┌─────────────────────────┐
                          │  macOS Keychain         │
                          │  (refresh tokens only)  │
                          └─────────────────────────┘
```

### Modules

All under `src/ogmac/`:

| Module | Responsibility | Key external deps |
|---|---|---|
| `cli.py` | Entry point: `sync`, `login`, `status`, `resume`, `reset` subcommands. | `argparse` |
| `config.py` | Load YAML config, validate, expose typed dataclasses. | `pydantic` |
| `auth.py` | OAuth flows for both providers, token refresh, Keychain I/O. | `msal`, `google-auth`, `keyring` |
| `outlook.py` | Read source events from Graph: window query, recurrence expansion, normalization to internal `SourceEvent` shape. | `httpx`, `msal` |
| `google.py` | Write target events to Calendar v3: create / update / delete with `extendedProperties` markers. | `google-api-python-client` |
| `reconciler.py` | Pure diff: `(sources, targets, state) → list[Action]`. **No I/O.** | — |
| `state.py` | SQLite wrapper: event mapping, run state (failure counter, disabled flag). | `sqlite3` (stdlib) |
| `notify.py` | Failure notifications via `osascript`. | `subprocess` |
| `logging_setup.py` | Rotating file handler at `~/Library/Logs/ogmac/sync.log`. | `logging` (stdlib) |
| `models.py` | `SourceEvent`, `TargetEvent`, `Action` dataclasses. | — |

### Data flow per sync run

1. `cli.py sync` parses args, sets up logging, loads config.
2. Check `run_state.disabled` — if set, log and exit 0 (do not let launchd see repeated failures).
3. `auth.py` ensures both tokens are valid (silent refresh; if refresh fails, increment failure counter, notify, exit non-zero — never pop a browser from a background run).
4. `outlook.py` pulls events in window `[now − 1d, now + 30d]`, returns `list[SourceEvent]`.
5. `google.py` pulls existing events with the `ogmac_owned` marker in the same window, returns `list[TargetEvent]`.
6. `reconciler.py` joins these against `state.db` mappings → emits `list[Action]` (CREATE / UPDATE / DELETE / SKIP).
7. `cli.py` dispatches actions through `google.py`, updating `state.db` after each successful API call.
8. On clean run: reset failure counter, log success. On failure: increment counter, possibly notify, possibly self-disable.

### Why this shape

- `reconciler.py` is a pure function, trivially unit-testable with synthesized inputs. All I/O lives at the edges.
- `state.db` is the source of truth for "what we created last time" — without it, deletions can't be reliably detected and we can't distinguish events we created vs. events the user added by hand.
- Strict separation between "events we own" (marked with `extendedProperties.private.ogmac_owned`) and "events the user owns" — we never read, modify, or delete events without our marker.

---

## §2. Sync algorithm

### Window definition

At each run: `start = now() − 1d`, `end = now() + 30d`, both UTC. Both sides queried over the same window.

### Source pull (Outlook → Graph)

`GET /me/calendarView?startDateTime={start}&endDateTime={end}` — this endpoint **returns recurring series already expanded into individual instances**, so client-side expansion is not needed. Page through `@odata.nextLink` until exhausted.

Each event is normalized to:

```python
@dataclass(frozen=True)
class SourceEvent:
    outlook_id: str          # event id (master id for instances of a series)
    instance_id: str         # unique per occurrence — id field on the instance
    subject: str
    start_utc: datetime
    end_utc: datetime
    location: str | None
    body_text: str           # body.content, sanitized to plain text
    last_modified: datetime  # for change detection
    is_cancelled: bool       # cancelled occurrences arrive as type=occurrence with isCancelled=true
```

`instance_id` is the join key. One Google event per Outlook *occurrence*, never per series.

### Target pull (Google Calendar v3)

```
events.list(
    calendarId=<target>,
    timeMin=start, timeMax=end,
    singleEvents=True, showDeleted=False,
    privateExtendedProperty="ogmac_owned=1",
)
```

This filter ensures we only see events we created. Anything else in the calendar is the user's own and is invisible to ogmac.

```python
@dataclass(frozen=True)
class TargetEvent:
    google_id: str
    etag: str
    instance_id: str   # from extendedProperties.private.ogmac_instance_id
    last_synced_outlook_modified: datetime  # from extendedProperties.private.ogmac_source_modified
```

### Reconciliation (pure)

Inputs: `list[SourceEvent]`, `list[TargetEvent]`. Output: `list[Action]`.

Build maps `S = {ev.instance_id: ev for ev in sources if not ev.is_cancelled}` and `T = {ev.instance_id: ev for ev in targets}`. For each `instance_id` in `S ∪ T`:

| Source has it? | Target has it? | Outlook `last_modified` > stored? | Action |
|---|---|---|---|
| Yes | No | — | **CREATE** in Google |
| Yes | Yes | Yes | **UPDATE** in Google (overwrite) |
| Yes | Yes | No | **SKIP** (no change) |
| No (or cancelled) | Yes | — | **DELETE** in Google |
| No | No | — | impossible |

Notes:

- **Drift policy B1 (overwrite manual Google edits)** is implicit: change detection compares Outlook's `last_modified` against `ogmac_source_modified` stored on the Google event. We do not read Google's etag to detect drift; if the user edited the Google copy, we won't notice — but on the next Outlook change we overwrite cleanly. This is the desired behavior.
- **Drift policy A1 (delete-on-source-delete)** covers three cases:
  - Outlook event deleted → not present in source pull → DELETE.
  - Recurring instance cancelled → present as `is_cancelled=true`, filtered out of `S` → DELETE.
  - Outlook event moved outside the window → not present → DELETE. Acceptable side effect of a tight window: an event moved from "tomorrow" to "60 days from now" disappears from Google until it slides back in.

### Action dispatch

Each action is applied through `google.py`:

**CREATE:**

```python
event_body = {
    "summary": src.subject,
    "location": src.location,
    "description": src.body_text,
    "start": {"dateTime": src.start_utc.isoformat(), "timeZone": "UTC"},
    "end":   {"dateTime": src.end_utc.isoformat(),   "timeZone": "UTC"},
    "extendedProperties": {"private": {
        "ogmac_owned": "1",
        "ogmac_instance_id": src.instance_id,
        "ogmac_source_modified": src.last_modified.isoformat(),
    }},
    # NO attendees field, by design
}
google_id = service.events().insert(calendarId=cfg.target, body=event_body).execute()["id"]
state.put(src.instance_id, google_id, src.last_modified)
```

**UPDATE:** same body, `service.events().update(calendarId=cfg.target, eventId=tgt.google_id, body=event_body).execute()`. Update `state` row.

**DELETE:** `service.events().delete(calendarId=cfg.target, eventId=tgt.google_id).execute()`. Remove `state` row.

### Idempotency and crash safety

The whole sync is idempotent — rerunning produces the same end state. Each action commits its DB row immediately after the successful Google API call; no batched transactions. Cost: a crash mid-batch may leave one in-flight action un-recorded.

- UPDATE and DELETE are naturally idempotent.
- CREATE is made idempotent through duplicate prevention: before inserting, query Google for any existing event with `privateExtendedProperty=ogmac_instance_id={instance_id}`. If one exists (orphan from a prior crashed run), adopt it — write its `google_id` into `state.db` and treat the action as UPDATE.

### State DB role

The state DB is **belt-and-suspenders** alongside `extendedProperties`. In principle we could reconstruct everything from `extendedProperties` alone, but the DB lets us:

- Quick lookup without re-pulling everything (used during retry).
- Detect orphan rows whose `instance_id` is gone from both sides → cleanup.
- Persist the failure counter, last successful sync timestamp, and disabled flag.

---

## §3. Auth, config, state

### Microsoft Graph OAuth

- **Client ID:** `14d82eec-204b-4c2f-b7e8-296a70dab67e` (Microsoft Graph Command Line Tools — public client, pre-trusted in most M365 tenants).
- **Authority:** `https://login.microsoftonline.com/common` (MSAL discovers the tenant).
- **Scopes:** `Calendars.Read`. Read-only — we never write back to Outlook.
- **Flow:** `msal.PublicClientApplication.acquire_token_interactive(port=0)`. Browser opens once during `ogmac login`.
- **Refresh:** `acquire_token_silent()` first; on failure during a background `sync` run, log and exit non-zero — do **not** open a browser.

### Google Calendar OAuth

- **Client ID:** user-supplied. Google does not publish well-known public desktop clients; the user creates an OAuth client of type "Desktop app" in their personal `console.cloud.google.com` project. Config holds the path to the downloaded `client_secret.json`.
- **Scopes:** `https://www.googleapis.com/auth/calendar.events` — write events on calendars the user owns; does not list other calendars. `calendar` scope is avoided as we don't manage calendars.
- **Flow:** `google_auth_oauthlib.flow.InstalledAppFlow.run_local_server(port=0)` during `ogmac login`.
- **Refresh:** `Credentials.refresh(Request())` automatic via the client library.

### Token storage — macOS Keychain

Both providers' refresh material lives in Keychain via the `keyring` Python library (which uses `Security.framework`).

| Service name | Account | Stored value |
|---|---|---|
| `ogmac.microsoft` | UPN, e.g. `you@example.com` | MSAL serialized cache (JSON blob) |
| `ogmac.google` | gmail address | `Credentials.to_json()` |

No plaintext tokens ever touch disk.

### Config file

Location: `~/.config/ogmac/config.yaml`. Created by `ogmac login` on first run, hand-editable thereafter.

```yaml
outlook:
  account: you@example.com              # UPN, used as Keychain account name
  source_calendar: default              # "default" or a specific Outlook calendar ID

google:
  account: <gmail>                      # used as Keychain account name
  client_secret_path: ~/.config/ogmac/google_client_secret.json
  target_calendar_id: <google calendar id>   # the dedicated "Work (synced)" calendar

sync:
  window_past_days: 1
  window_future_days: 30
  interval_seconds: 900                  # informational; launchd plist is the source of truth

privacy:
  copy_subject: true
  copy_location: true
  copy_body: true
  copy_attendees: false                  # locked false; validation rejects true

failure:
  max_consecutive_before_disable: 5
  notify_on_failure: true
```

Validation: parsed into a `pydantic.BaseModel` on load. Bad config → exit non-zero with a clear message. Missing fields fall back to the defaults above.

### State DB schema

SQLite at `~/Library/Application Support/ogmac/state.db`. Single connection per process, `journal_mode=WAL` for crash safety.

```sql
CREATE TABLE IF NOT EXISTS event_map (
    instance_id              TEXT PRIMARY KEY,    -- Outlook occurrence id
    google_id                TEXT NOT NULL,
    last_source_modified     TEXT NOT NULL,       -- ISO-8601 UTC
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_google_id ON event_map(google_id);

CREATE TABLE IF NOT EXISTS run_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- keys used:
--   "consecutive_failures" -> int as string
--   "last_success_at"      -> ISO-8601 UTC
--   "disabled"             -> "1" if auto-disabled, absent otherwise
--   "disable_reason"       -> human-readable string (when disabled="1")
```

Schema is created idempotently on every startup. Future schema changes will use a `schema_version` row and a migrator — not built in v1.

### Reset / recovery

`ogmac reset`:

- Wipes `event_map` rows.
- Deletes all events in the target Google calendar where `extendedProperties.private.ogmac_owned == "1"`.
- Clears `run_state` (failure counter, disabled flag).
- Does **not** touch tokens (re-auth is `ogmac login`).

---

## §4. Operational concerns

### launchd plist

Path: `~/Library/LaunchAgents/com.ogmac.sync.plist`. Loaded with:

```bash
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.ogmac.sync.plist
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ogmac.sync</string>

    <key>ProgramArguments</key>
    <array>
        <string>__OGMAC_PYTHON__</string>
        <string>-m</string>
        <string>ogmac.cli</string>
        <string>sync</string>
    </array>

    <key>StartInterval</key>
    <integer>900</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>__OGMAC_LOG_DIR__/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>__OGMAC_LOG_DIR__/launchd.err.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin</string>
    </dict>

    <key>ProcessType</key>
    <string>Background</string>

    <key>LowPriorityIO</key>
    <true/>

    <key>Nice</key>
    <integer>10</integer>
</dict>
</plist>
```

Behavior:

- `StartInterval=900` → 15 min, drift-aware (re-fires 900 s after the previous *completion*). Skips during sleep, fires immediately on wake.
- `RunAtLoad=true` → first sync at login, not 15 min later.
- `ProcessType=Background` + `LowPriorityIO` + `Nice=10` → battery-friendly, respects App Nap and Low Power Mode.
- No `KeepAlive` — process exits after each run.
- launchd's stdout/stderr go to a separate file from the app's structured log so we can distinguish "Python crashed before logging started" from app-level errors.

### Logging

`~/Library/Logs/ogmac/sync.log`. Rotating: 10 files × 1 MB each via `logging.handlers.RotatingFileHandler`. Format:

```
2026-04-28T14:32:01Z INFO  sync.start    window=[2026-04-27..2026-05-28]
2026-04-28T14:32:02Z INFO  outlook.fetch count=47 pages=1
2026-04-28T14:32:03Z INFO  google.fetch  count=44
2026-04-28T14:32:03Z INFO  reconcile     create=2 update=1 delete=0 skip=44
2026-04-28T14:32:04Z INFO  google.create instance=AAMkA... google_id=abc123
2026-04-28T14:32:05Z INFO  sync.success  duration_ms=3210
```

Levels:

- `DEBUG` — HTTP request/response bodies. Off by default; toggle via `OGMAC_DEBUG=1`.
- `INFO` — sync flow as above.
- `WARNING` — retry attempts.
- `ERROR` — terminal failures.

**Never log** event subjects, bodies, locations, or attendee lists. Log only: instance IDs, counts, durations, error types. (Logs are plaintext on disk; treat work calendar contents as not-for-disk.)

### Failure tracking & self-disable

In-DB counter at `run_state.consecutive_failures`. After each sync attempt:

```python
def finalize(success: bool, error: Exception | None):
    if success:
        state.set("consecutive_failures", "0")
        state.set("last_success_at", utcnow_iso())
        return

    n = int(state.get("consecutive_failures", "0")) + 1
    state.set("consecutive_failures", str(n))
    log.error("sync.failure n=%d type=%s", n, type(error).__name__)

    if n >= cfg.failure.max_consecutive_before_disable:
        state.set("disabled", "1")
        state.set("disable_reason", f"{n} consecutive failures: {error}")
        notify(title="ogmac auto-disabled",
               body=f"{n} consecutive failures. Run 'ogmac status' and 'ogmac resume'.",
               sticky=True)
    elif n == 1:
        notify(title="ogmac sync failed", body=f"{type(error).__name__}: {error}")
```

Notification policy: notify once at `n=1` (early signal — token expired this morning), stay silent at `n=2..4`, and post a sticky alert at `n=5` when the auto-disable triggers. No double-notification at the disable threshold.

On the next launchd-fired run, `cli.py sync` checks `run_state.disabled` first and exits 0 immediately if set, so launchd does not see repeated failures and does not throttle the job. Re-enabling is explicit:

- `ogmac status` — prints `disabled`, `reason`, `last_success_at`, exit code reflects state.
- `ogmac resume` — clears `disabled` and `consecutive_failures`, runs one sync immediately.

### Notifications

Native banner via `osascript`:

```python
subprocess.run([
    "osascript", "-e",
    f'display notification {json.dumps(body)} with title {json.dumps(title)}'
])
```

No third-party dependency (`terminal-notifier` would add Homebrew baggage). Sticky alerts (auto-disable case) use `display alert` via a detached `osascript` so the dialog stays until dismissed. If `osascript` itself is broken, the log still has the error.

### App Nap / Low Power Mode

`ProcessType=Background` opts in. Behaviors accepted:

- On battery + Low Power Mode: launchd may delay the fire by tens of seconds to coalesce wakeups.
- Lid closed: no fires. On wake: one immediate fire (covers freshness).
- Clamshell + power: normal cadence.

If a sync gets delayed, the next one catches up — no special handling needed.

---

## §5. Testing & project layout

### Project layout

```
ogmac/
├── README.md                        # install, login, launchd setup, troubleshooting
├── pyproject.toml                   # build + deps (PEP 621)
├── .gitignore
├── .python-version                  # 3.11
├── src/
│   └── ogmac/
│       ├── __init__.py
│       ├── __main__.py              # `python -m ogmac` → cli.main()
│       ├── cli.py                   # subcommands: sync, login, status, resume, reset
│       ├── config.py
│       ├── auth.py
│       ├── outlook.py
│       ├── google.py
│       ├── reconciler.py
│       ├── state.py
│       ├── notify.py
│       ├── logging_setup.py
│       └── models.py
├── tests/
│   ├── unit/
│   │   ├── test_reconciler.py       # bulk: pure function, table-driven
│   │   ├── test_state.py            # SQLite round-trips, schema bootstrap
│   │   ├── test_config.py           # validation, defaults, missing fields
│   │   └── test_normalization.py    # Graph payload → SourceEvent
│   ├── integration/
│   │   ├── test_graph_live.py       # opt-in via OGMAC_LIVE=1
│   │   └── test_google_live.py      # opt-in via OGMAC_LIVE=1
│   ├── e2e/
│   │   └── test_full_run.py         # mocked APIs, real cli.main, real SQLite
│   └── fixtures/
│       ├── graph_calendarview_page.json
│       ├── graph_recurring_expanded.json
│       └── google_events_list.json
├── packaging/
│   ├── com.ogmac.sync.plist         # launchd template, paths interpolated by installer
│   └── install.sh                   # creates venv, installs deps, writes plist, bootstraps
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-04-28-ogmac-design.md
```

### Testing strategy

**Pure layer (high coverage, fast):**

- `reconciler.py` — table-driven tests covering every row of the diff matrix in §2, plus:
  - source-only (CREATE)
  - target-only (DELETE)
  - both, no change (SKIP)
  - both, source modified (UPDATE)
  - source cancelled occurrence (DELETE)
  - source moved out of window (DELETE — same path as missing)
  - target without `ogmac_owned` marker (filtered before reconciler — assert reconciler never sees it)
  - duplicate adoption (target with our marker but no DB row → reconciler emits UPDATE, not CREATE)
- `models.py` / normalization — given a frozen Graph JSON fixture, assert the resulting `SourceEvent` matches expected.
- `config.py` — bad YAML, missing fields, `copy_attendees=true` (rejected — locked false).
- `state.py` — write/read/delete round-trips, failure-counter increment/reset, disabled flag.

**Boundary layer (mocked):**

- `outlook.py`, `google.py` — `pytest-httpx` / `respx` for HTTP mocking. Verify pagination, retry on 429/5xx with exponential backoff, correct query params, `extendedProperties` written/read correctly.

**Integration layer (live, opt-in):**

- Two scripts gated by `OGMAC_LIVE=1`. Throwaway Google calendar named `ogmac-test`. Outlook side reads only. CI never runs these; the author runs them locally before a release.

**End-to-end smoke:**

- `tests/e2e/test_full_run.py` — ephemeral SQLite, both APIs mocked with realistic fixtures. Runs `cli.main(["sync"])`, asserts the right HTTP calls were made and the DB ended in expected state.

**Out of test scope:**

- launchd plist syntax — manually verified once.
- `osascript` notifications — visually confirmed once.
- Keychain integration — relies on `keyring` lib's tests; we mock `keyring` in unit tests.

**Coverage targets:** ≥ 90% on `reconciler.py`, `state.py`, `config.py`, `models.py`. Boundary modules and `cli.py` lower (orchestration is hard to unit-test cleanly).

**TDD posture:** `reconciler.py` is written test-first — the diff matrix is the spec, tests encode the matrix, implementation falls out. Other modules pragmatic test-after.

### Dependencies (`pyproject.toml`)

```toml
[project]
name = "ogmac"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "msal>=1.28",
  "google-auth>=2.29",
  "google-auth-oauthlib>=1.2",
  "google-api-python-client>=2.130",
  "httpx>=0.27",
  "keyring>=25.0",
  "pydantic>=2.7",
  "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-httpx>=0.30",
  "pytest-cov>=5.0",
  "ruff>=0.4",
  "mypy>=1.10",
]

[project.scripts]
ogmac = "ogmac.cli:main"
```

Total install footprint: ~50 MB in venv (Google client lib is the heavy one).

---

## Out of scope (v1)

Recorded so future-me does not second-guess:

- Two-way sync.
- Multiple calendar pairs.
- Categories / colors / reminders mapping.
- Attachment handling.
- Free/busy-only mode (we copy details).
- Webhooks / push notifications from Graph.
- Any GUI.
- Multi-user packaging.
- Auto-update mechanism.
- Classic Outlook for Mac AppleScript path.
- EWS fallback.

---

## §6. Deviations from design (as-built, 2026-04-28)

### Outlook backend: now config-selectable (`apple_calendar` default, `microsoft_graph` opt-in)

**Why:** the public Graph CLI client ID `14d82eec-204b-4c2f-b7e8-296a70dab67e` is gated by admin consent on many corporate Microsoft 365 tenants. When the consent request sits unapproved, there is no path to self-service. Initial pivot was to replace Graph wholesale with EventKit; we then kept Graph as an opt-in alternative for users on tenants without that gate.

**What changed:**

- New config field `outlook.read_method: Literal["apple_calendar", "microsoft_graph"] = "apple_calendar"`. Pydantic enforces the value set; default is `apple_calendar` (the friction-free path on Mac).
- `outlook_eventkit.py` was added (PyObjC against EventKit) alongside the original `outlook.py` (Graph + MSAL + httpx). Both expose the same `fetch_source_events(token, source_calendar, start, end) -> list[SourceEvent]` signature. EventKit ignores the token arg.
- `cli._run_sync` branches on `cfg.outlook.read_method` to pick the reader; `get_graph_token` is only called for the `microsoft_graph` path.
- `cli._cmd_login` is read-method-aware: `ogmac login` (no provider) only invokes Microsoft login when `read_method=microsoft_graph`; `ogmac login microsoft` is rejected with a clear message when `read_method=apple_calendar`.

**Module map update:**

| Module | Status |
|---|---|
| `outlook.py` (Graph) | retained, used only when `read_method=microsoft_graph` |
| `outlook_eventkit.py` | added; used when `read_method=apple_calendar` |
| `cli.py` | imports both backends; runtime branch in `_run_sync` and `_cmd_login` |
| `auth.py` | Microsoft helpers retained, only exercised on the Graph path |

**Trade-offs (apple_calendar):**

- ogmac inherits whatever Calendar.app shows. Privacy stripping (no attendees in Google) is enforced by ogmac code, not by an OAuth scope ceiling.
- A few-minute Exchange→EventKit sync delay sits in front of every ogmac run.
- Permission surface moves from cloud to local: ogmac requires the user to approve Calendar access for the Python binary in System Settings → Privacy & Security → Calendars on first run.

**Trade-offs (microsoft_graph):**

- Requires admin-consented Graph CLI client on the tenant. Not viable on locked-down corporate tenants.
- No dependency on Calendar.app or Exchange-in-Internet-Accounts.

### Availability sync (Free / Busy / Tentative / Out of Office)

**Why:** the original spec stripped availability — every synced event in Google was opaque-busy, which made all-day OOO events from coworkers occupy the user's day visually.

**What changed:** `SourceEvent` gained an `availability: str` field. EventKit `EKEventAvailability` is mapped to a string; Google body sets `transparency` and (for OOO) `eventType`:

| EventKit `availability()` | `SourceEvent.availability` | Google body |
|---|---|---|
| `EKEventAvailabilityFree` (1) | `"free"` | `transparency: "transparent"` |
| `EKEventAvailabilityBusy` (0) or NotSupported (-1) | `"busy"` | `transparency: "opaque"` |
| `EKEventAvailabilityTentative` (2) | `"tentative"` | `transparency: "opaque"` |
| `EKEventAvailabilityUnavailable` (3) | `"outOfOffice"` | `eventType: "outOfOffice"` + `transparency: "opaque"` |

### All-day events use Google's `date` format

**Why:** all-day events in EventKit (`event.isAllDay() == True`) report start/end as the local-midnight-to-23:59:59 UTC pair. Sending those to Google as `dateTime` produces a 24-hour timed block instead of the thin all-day strip.

**What changed:** `SourceEvent` gained `is_all_day: bool`. `google.py` branches on it: timed events use `{dateTime, timeZone: "UTC"}`; all-day events use `{date: "YYYY-MM-DD"}` with the date taken in the system local timezone, and the end date bumped by +1 day (Google's all-day end is exclusive).

### Google Cloud Console steps (made explicit in README)

The original spec said only "user creates an OAuth client of type Desktop app." The README now spells out each click: enable the Calendar API in the Library, set up the OAuth consent screen with the Gmail address as a Test user, create the Desktop OAuth client, download `client_secret.json`. The first sync without Calendar API enabled fails with `accessNotConfigured`; that is now called out in Troubleshooting.

### Test fixture impact

- `SourceEvent` field additions (`availability`, `is_all_day`) are defaulted (`"busy"`, `False`) so existing fixtures keep working without edits.
- `tests/e2e/test_full_run.py` was updated: `TestTokenRefreshFailure` and `TestAutoDisableThreshold` previously patched `ogmac.cli.get_graph_token`; that path is no longer hit. They now patch `get_google_credentials` with the same `TokenRefreshError`, since that is the only token-refresh point left in the sync path.
- An autouse `_no_real_logging` fixture was added in `test_full_run.py` to prevent `setup_logging()` from leaving a real `RotatingFileHandler` on the root logger, which otherwise broke later test_logging_setup assertions.

Final test status: 158 passed, 2 skipped.
