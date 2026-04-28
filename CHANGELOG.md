# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/razbahri/ogmac/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/razbahri/ogmac/releases/tag/v0.1.0
