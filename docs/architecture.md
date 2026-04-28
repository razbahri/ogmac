# Architecture

A short tour of how ogmac maps Outlook events to Google, and how it stays out of the way of events you create yourself.

## Sync model

ogmac is a **stateless reconciler** with a small local cache. Each run:

1. **Fetch** source events from Outlook (via EventKit or Graph) within the configured window.
2. **Fetch** target events from Google (filtered to `ogmac_owned=1`) within the same window.
3. **Reconcile** in memory — pure function, fully tested. Output: a list of `CREATE | UPDATE | DELETE | SKIP` actions.
4. **Apply** each action via the Google Calendar API.
5. **Persist** the run result (last success, failure counter) to local SQLite.

The reconciler has no I/O — all network and filesystem effects happen at the edges (`cli.py`). This keeps the diff logic easy to test and easy to reason about.

## Field mapping

| Outlook | Google Calendar |
|---|---|
| `title` / `subject` | `summary` |
| `location` | `location` |
| `notes` / `body` | `description` |
| `startDate` / `endDate` *(timed)* | `start.dateTime` / `end.dateTime` (UTC) |
| `startDate` / `endDate` *(all-day)* | `start.date` / `end.date` (local; end is exclusive +1 day) |
| `availability=Free` | `transparency: transparent` |
| `availability=Busy` or `Tentative` | `transparency: opaque` |
| `availability=Unavailable` *(Out of Office)* | `eventType: outOfOffice` + `transparency: opaque` |
| Attendees | **Stripped — never copied** |
| Cancelled occurrence | Deleted from Google |

## Identity & ownership

Every event ogmac creates is stamped via `extendedProperties.private`:

| Key | Purpose |
|---|---|
| `ogmac_owned=1` | Ownership marker. Every `events.list` query filters by this — user-created events on the target calendar are **invisible** to ogmac. |
| `ogmac_instance_id` | Outlook occurrence id. Reconciliation join key (matches a Google event back to its source). |
| `ogmac_source_modified` | Outlook `lastModifiedDate`. UPDATE fires when the source value is newer than the stored one. |

This is why you can point ogmac at a calendar you also use manually: it cannot see, modify, or delete anything it didn't create.

## Backends

ogmac has two interchangeable Outlook readers behind a uniform `SourceEvent` model. Switching is a one-line config change.

```
                   ┌────────────────────────┐
                   │  cli.py (orchestrator) │
                   └───────────┬────────────┘
                               │
                cfg.outlook.read_method
                  │                     │
        apple_calendar          microsoft_graph
                  │                     │
                  ▼                     ▼
       ┌──────────────────┐   ┌──────────────────┐
       │ outlook_eventkit │   │     outlook      │
       │ (PyObjC/EventKit)│   │ (Graph REST/httpx)│
       └──────────────────┘   └──────────────────┘
                  │                     │
                  └──────────┬──────────┘
                             ▼
                       SourceEvent[]
                             │
                  ┌──────────▼──────────┐
                  │     reconciler      │  pure function
                  └──────────┬──────────┘
                             ▼
                          Action[]
                             │
                  ┌──────────▼──────────┐
                  │      google.py      │
                  └─────────────────────┘
```

### `apple_calendar` (EventKit)

Uses `pyobjc-framework-EventKit` to read events directly from the macOS calendar database. The Outlook account must be configured in **System Settings → Internet Accounts** so Calendar.app populates the data; ogmac then reads it.

- No Microsoft OAuth.
- Inherits Calendar.app's sync delay (typically minutes).
- Requires Calendar permission in **System Settings → Privacy & Security**.

### `microsoft_graph`

Uses MSAL + httpx to authenticate with the public **Graph CLI client** (`14d82eec-...`) and fetch via the [Calendar View API](https://learn.microsoft.com/graph/api/calendar-list-calendarview). The refresh token is stored exclusively in macOS Keychain.

- Requires admin consent on most enterprise tenants.
- No dependency on Calendar.app — the read path is fully independent of macOS.

## State

| Path | Contents |
|---|---|
| `~/Library/Application Support/ogmac/state.db` | SQLite — event-id mapping, run state, failure counter |
| Keychain `ogmac.google` | Google refresh token |
| Keychain `ogmac.microsoft` | Microsoft refresh token (only if `read_method: microsoft_graph`) |
| `~/.config/ogmac/config.yaml` | User config |
| `~/.config/ogmac/client_secret.json` | Google OAuth client (downloaded from Google Cloud Console) |
| `~/Library/Logs/ogmac/*.log` | Logs |

## Scheduling

`packaging/com.ogmac.sync.plist` is a launchd user agent:

- `RunAtLoad=true` → runs immediately at user login.
- `StartInterval=900` → every 15 minutes thereafter.
- `ProcessType=Background` + `LowPriorityIO=true` + `Nice=10` → polite to the rest of the system.
- Logs to `~/Library/Logs/ogmac/launchd.{out,err}.log`.

## Further reading

The full design rationale (including alternatives considered, reconciliation matrix, and rollout decisions) lives in [the design spec](superpowers/specs/2026-04-28-ogmac-design.md).
