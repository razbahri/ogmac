# ogmac menu bar app — design

**Status:** draft
**Author:** Raz
**Date:** 2026-05-08

## Goal

Add a minimal macOS menu bar app for ogmac that exposes three things:

1. **Status** — sync health at a glance.
2. **Settings** — view and edit the most-used config fields.
3. **History** — recent sync runs.

The app is the productized 1.0 face of ogmac: most users will never open the CLI again.

## Non-goals (v0.1)

- In-app OAuth / Google login flow. First-launch points users to `ogmac login` in Terminal.
- Replacing `install.sh`. A separate installation rework is happening in parallel.
- In-app calendar pickers (free-text calendar IDs for now).
- Notarization / code signing. Ship unsigned, distribute via Homebrew cask with `xattr` post-install.
- Reboot-persistent pause via `launchctl disable`. Pause is a flag in `state.db`; the daemon respects it.
- `failure.*` settings in the GUI (power-user knobs stay YAML-only).
- Push notification refinement. Existing `notify_on_failure` keeps its current behavior.
- "Syncing" icon state for launchd-driven runs. Only user-triggered syncs animate the icon.

## Architecture

Thin observer + commander. The Python daemon and `launchctl` schedule are unchanged; the app reads state and shells out for actions.

```
┌─────────────────────────┐         ┌──────────────────────────────────────┐
│  Swift menu bar app     │         │  Existing ogmac daemon               │
│  (LSUIElement, no Dock) │         │                                      │
│                         │  read   │  ~/.config/ogmac/config.yaml         │
│  Status panel  ────────►├────────►│  ~/Library/Application Support/      │
│  Settings sheet ───────►│  write  │      ogmac/state.db (SQLite)         │
│  History view  ────────►│  tail   │  ~/Library/Logs/ogmac/sync.log       │
│                         │         │                                      │
│  Sync now       ────────┼─Process─►  ogmac sync                          │
│  Resume         ────────┼─Process─►  ogmac resume                        │
│  Pause          ────────┼─Process─►  ogmac pause   (new subcommand)      │
│                         │         │                                      │
│                         │         │  launchd plist (every 15m)           │
└─────────────────────────┘         └──────────────────────────────────────┘
```

## Components

### Swift app modules

| Module | Responsibility |
|---|---|
| `OgmacApp` | App entry point, `LSUIElement`, `MenuBarExtra` |
| `StatusController` | Polls state every 5s when panel is open, every 60s when closed; derives icon state |
| `StateReader` | Read-only SQLite open against `state.db`; reads run state and the new `paused` flag |
| `LogReader` | Tails `sync.log`, parses the last N runs into structured records |
| `ConfigStore` | Loads, validates (light), and atomically writes `~/.config/ogmac/config.yaml` |
| `OgmacRunner` | Wraps `Process` invocations of the `ogmac` CLI |
| `MenuPanelView` | SwiftUI view for the dropdown |
| `SettingsScene` | SwiftUI `Settings` scene with three tabs |
| `HistoryView` | List of recent sync records |

### Python-side changes (small)

| Change | File | Purpose |
|---|---|---|
| Add `paused` flag to state | `state.py` | Mirror of `disabled` but user-set; survives reboots |
| `_run_sync` skips when paused | `cli.py` | Same pattern as `state.is_disabled` early return |
| New `ogmac pause` / `ogmac unpause` subcommands | `cli.py` | App invokes these instead of touching `state.db` directly |
| **Side fix:** drop dead `sync.interval_seconds` from `Config` | `config.py`, `docs/setup.md` | Currently never read; misleads users |

The Python diff is intentionally small. `state.db` writes stay in Python; the Swift app only reads it.

## Status

### Icon states

| State | SF Symbol / treatment | Condition |
|---|---|---|
| **Healthy** | `circle.fill` (accent tint) | `disabled=0`, `paused=0`, last success within `2 × interval` (i.e., within 30 minutes) |
| **Warning** | `exclamationmark.triangle.fill` (yellow) | `disabled=0`, `paused=0`, last success between 30 min and 24 h ago |
| **Error** | `xmark.octagon.fill` (red) | `disabled=0`, `paused=0`, last success > 24 h OR `consecutive_failures > 0` and last attempt failed |
| **Auto-disabled** | `xmark.octagon.fill` with badge | `disabled=1` (auto-disable triggered) |
| **Paused** | `pause.circle.fill` (grayscale) | `paused=1` |
| **Syncing** | rotating `arrow.triangle.2.circlepath` | A user-triggered `Sync now` is in flight (process is alive) |
| **Needs login** | `circle` (hollow) | Token-refresh failure detected on last run (parsed from log: `TokenRefreshError`) |

State is mutually exclusive. Resolution order: Syncing → Paused → Auto-disabled → Needs login → Error → Warning → Healthy.

### Dropdown panel

```
┌────────────────────────────────────┐
│ ogmac                  ● Healthy   │
│ Last sync · 2 min ago              │
│ Next sync · in 13 min              │
│                                    │
│ Read   Outlook (EventKit)          │
│ Write  Work (synced) — Google      │
│                                    │
│ Last run                           │
│   ✓ 14 created · 2 updated · 1 del │
│                                    │
│ ┌────────────────────────────────┐ │
│ │          Sync now              │ │
│ └────────────────────────────────┘ │
│                                    │
│ Settings…                          │
│ History…                           │
│ Pause                              │
│ Quit ogmac                         │
└────────────────────────────────────┘
```

- "Next sync" is computed from the plist's `StartCalendarInterval` (next of :00/:15/:30/:45 from now).
- "Last run" is the most recent `reconcile create=… update=… delete=… skip=…` line in `sync.log`.
- "Read" / "Write" labels derive from `outlook.read_method` and `google.target_calendar_id` (resolve calendar name once via `ogmac` if available; otherwise show the ID).

## Settings

Native macOS `Settings` scene, three tabs.

### Connection tab

| Field | Type | Bound to | Notes |
|---|---|---|---|
| Read backend | Segmented picker | `outlook.read_method` | `apple_calendar` / `microsoft_graph` |
| Outlook account | Text field | `outlook.account` | |
| Outlook source calendar | Text field | `outlook.source_calendar` | Free-text in v0.1 |
| Google account | Text field | `google.account` | |
| Google client secret path | Path field with "Choose…" | `google.client_secret_path` | |
| Google target calendar ID | Text field | `google.target_calendar_id` | Free-text in v0.1 |

Switching read backend shows an inline note: "You may need to run `ogmac login microsoft` in Terminal."

### Sync tab

| Field | Type | Bound to |
|---|---|---|
| Window — past | Stepper (1–30 days) | `sync.window_past_days` |
| Window — future | Stepper (1–365 days) | `sync.window_future_days` |
| Schedule | Read-only text + "Edit in plist…" link | `StartCalendarInterval` from plist |

Schedule is **read-only** in v0.1. Editing `StartCalendarInterval` requires writing the plist + `launchctl bootout`/`bootstrap`. Out of scope; documented as known limitation.

### Privacy tab

| Field | Type | Bound to |
|---|---|---|
| Copy subject | Toggle | `privacy.copy_subject` |
| Copy location | Toggle | `privacy.copy_location` |
| Copy body | Toggle | `privacy.copy_body` |
| Copy attendees | Toggle (locked off, disabled) | `privacy.copy_attendees` |

The locked attendees toggle has a tooltip: "Attendee syncing is disabled by design. See README → Privacy."

### Settings persistence

- Source of truth: `~/.config/ogmac/config.yaml`.
- Writes are atomic: write to `config.yaml.tmp`, `fsync`, `rename` over the original.
- The app loads on open and on save; no in-memory cache between sessions.
- Validation: minimal (non-empty strings, integer ranges). The Python `Config.load` will reject a bad write on the next sync; the app surfaces that via the icon's Error state, not a save-time block.

## History

Sheet listing the last 50 sync runs.

| Column | Source |
|---|---|
| Started at | `sync.start` line timestamp |
| Result | `sync.success` or `sync.failure` |
| Duration | `duration_ms` from `sync.success` |
| Counts | `reconcile create=N update=N delete=N skip=N` |

Implementation: `LogReader` scans `sync.log` (and rotated `sync.log.1…sync.log.10`) line by line, groups lines into runs by start/end markers. No structured runs table in v0.1 — defer to v0.2 if the parser becomes a maintenance burden.

## Actions

| Menu item | Implementation |
|---|---|
| Sync now | `Process` running `ogmac sync`; icon shows Syncing while alive |
| Pause | `Process` running `ogmac pause`; icon flips to Paused |
| Resume (when paused) | `Process` running `ogmac unpause` |
| Resume (when auto-disabled) | `Process` running `ogmac resume` |
| Settings… | Open Settings scene |
| History… | Open History sheet |
| Quit ogmac | Quit the menu bar app (does **not** stop launchd; tooltip clarifies) |

`ogmac` binary path resolution: try `which ogmac` via `/usr/bin/env`, fall back to `~/.local/share/ogmac/venv/bin/ogmac` (the install.sh path). If neither exists, the app shows an "ogmac CLI not found" first-launch screen.

## State and IPC contract

| Resource | Owner | Reader | Writer |
|---|---|---|---|
| `~/.config/ogmac/config.yaml` | User | App, daemon | App |
| `~/Library/Application Support/ogmac/state.db` | Daemon | App (read-only), daemon | Daemon only |
| `~/Library/Logs/ogmac/sync.log` | Daemon | App (read-only), daemon | Daemon |
| `~/Library/LaunchAgents/com.ogmac.sync.plist` | install.sh | App (read-only) | install.sh |

The app never writes to `state.db` or the plist in v0.1.

## App lifecycle

- `Info.plist`: `LSUIElement = true` (no Dock icon, no `App` menu).
- "Launch at login" toggle in Settings → Sync tab, implemented via `SMAppService.mainApp`.
- Quit removes the menu bar item but does **not** stop launchd. Tooltip on the menu item makes this explicit.

## Distribution

- Build: `xcodebuild` produces an unsigned `.app`.
- Distribute: Homebrew cask with `postflight` block running `xattr -d com.apple.quarantine "/Applications/ogmac.app"`.
- When sponsor lands: enroll in Apple Developer Program, codesign with Developer ID, notarize, drop the `xattr` workaround. Cask spec gets the SHA updated; users transparently move to the signed build.

## EventKit / TCC

The Swift app does **not** read EventKit directly in v0.1. All Calendar reads stay in the Python daemon. The app therefore does **not** need `NSCalendarsUsageDescription`. (When calendar pickers ship in v0.2, the app will either: shell out to a new `ogmac list-calendars` CLI, or add the entitlement and prompt.)

## Side work (in scope, separate commit)

1. Drop `sync.interval_seconds` from `Config` and `docs/setup.md`. The field is never read; `StartCalendarInterval` in the plist is the only schedule source.
2. Add `paused` boolean to `state.db` run-state.
3. Add `ogmac pause` and `ogmac unpause` subcommands.
4. Make `_run_sync` early-return when `state.is_paused` (mirror of `state.is_disabled`).

## Testing

- **Unit (Swift):** `LogReader` parser against fixture `sync.log` files (success run, failure run, partial run, rotated logs). `ConfigStore` round-trip (load → mutate → save → reload).
- **Unit (Python):** `state.is_paused` flag set/unset; `_run_sync` skip path when paused.
- **Manual:** boot the app, observe each icon state by manipulating `state.db` (sqlite3 CLI), exercise Sync now / Pause / Resume, change a setting and verify the next sync picks it up.
- No automated UI tests in v0.1.

## Open questions deferred

- v0.2 calendar pickers (`ogmac list-calendars` JSON output).
- v0.2 schedule editing (write plist + reload).
- v0.2 structured `runs` table in `state.db`.
- v0.2 in-app `ogmac login` flow with `ASWebAuthenticationSession`.
