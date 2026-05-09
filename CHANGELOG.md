# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Sync window is now **day-aligned** in the user's local timezone — `[start_of(today − window_past_days) local, start_of(today + window_future_days + 1) local)`. Previously the window was relative to "now", which caused events near the past edge to slide out of scope mid-day (and get DELETEd from Google) and to flap CREATE/DELETE pairs across runs. Day-aligned means every sync of the same calendar day evaluates the same window.

## [0.2.0] - 2026-05-09

### Added
- **Menu bar app** (`Ogmac.app`) — SwiftUI status item that surfaces sync state, settings, and run history without a terminal. Built unsigned; install via `bash packaging/build_app.sh` then `open dist/Ogmac.app`. Spec: `docs/superpowers/specs/2026-05-08-menu-bar-app-design.md`. Plan: `docs/superpowers/plans/2026-05-08-menu-bar-app-team-breakdown.md`.
- File-system event watcher on `state.db` (DispatchSource). The panel refreshes within ~200 ms of each daemon write — no periodic polling, no missed updates regardless of sync duration.
- "Last change" panel row that shows the most recent run with non-zero CRUD activity, or "Up to date · checked X min ago" when only no-op syncs exist in the last 50 runs.
- History view with a "meaningful runs only" filter. Hides the every-2-min network-change-triggered no-op syncs; keeps real changes, failures, and the scheduled `:00`/`:15`/`:30`/`:45` ticks.
- Diagnostic log file at `~/Library/Logs/ogmac/menubar.log` with structured per-event lines for refresh activity, file-watcher events, and reader errors.
- `ogmac pause` and `ogmac unpause` subcommands. `_run_sync` early-returns when paused. The `paused` flag persists in `state.db` and survives reboots, mirroring the existing `disabled` pattern.
- Custom app bundle icon — dark squircle background with a white rounded-rectangle outline (`╭─╮ ╰─╯`), rendered programmatically in 7 sizes (16/32/64/128/256/512/1024 px).

### Changed
- `sync.interval_seconds` removed from the config schema. The field was never read; `StartCalendarInterval` in the launchd plist is the only schedule source. Existing configs that still contain the field are silently accepted with a deprecation warning.
- Minimum macOS for the menu bar app is **14.0** (the panel uses `@Environment(\.openSettings)`, which is macOS 14+). The Python daemon's minimum is unchanged.

## [0.1.0] - 2026-04-28

Initial release.

### Added
- One-way sync from Outlook (Microsoft 365 / Exchange) to a dedicated Google Calendar.
- Two interchangeable Outlook backends, selectable in `config.yaml` via `outlook.read_method`:
  - `apple_calendar` (default) — reads via Apple's EventKit framework; no Microsoft OAuth.
  - `microsoft_graph` — reads via the Microsoft Graph API using the public Graph CLI client.
- Availability mapping: Outlook Free / Busy / Tentative / Out of Office → Google `transparency` and `eventType: outOfOffice`.
- All-day event handling: written to Google as date-only events with exclusive end date.
- Local SQLite state for instance-id mapping, run state, and consecutive-failure counter.
- Auto-disable after `failure.max_consecutive_before_disable` consecutive failures, with a macOS notification.
- CLI commands: `sync`, `status`, `login [google|microsoft]`, `resume`, `reset [--yes]`.
- launchd integration via `packaging/install.sh` (15-minute schedule, log rotation).
- Refresh tokens stored exclusively in macOS Keychain (`ogmac.google`, `ogmac.microsoft`).

[Unreleased]: https://github.com/razbahri/ogmac/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/razbahri/ogmac/releases/tag/v0.2.0
[0.1.0]: https://github.com/razbahri/ogmac/releases/tag/v0.1.0
