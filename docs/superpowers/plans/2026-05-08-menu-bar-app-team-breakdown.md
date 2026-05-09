# ogmac menu bar app — Agent Team Breakdown

**Source spec:** `docs/superpowers/specs/2026-05-08-menu-bar-app-design.md`
**Date:** 2026-05-08
**Purpose:** How to parallelize the v0.1 menu bar app across a team of subagents — roles, file ownership, dependencies, and execution waves.

---

## Headcount

**7 specialist agents + 1 orchestrator (you).**

Decomposition principle, same as v1: split by *responsibility boundary*, not by file count. The Swift app is layered into adapters → commander → views → integrator. The Python diff is its own agent because it runs in parallel with the Swift scaffold and ships independently.

| ID | Role | Layer |
|---|---|---|
| F | Foundation (Swift scaffold) | scaffolding |
| P | Python diff (pause + side fix) | daemon |
| R | Read adapters | I/O (read-only) |
| C | Commander | I/O (subprocess) |
| V | Views (status + history) | UI |
| G | Settings UI | UI |
| I | Integrator + Packaging | wiring + ops |

---

## Execution waves

```
Wave 0 ── F ─────────────────────────────────────►
       └─ P ─────────────────────────────────────►
              │
              ├── Wave 1 ── R ────────────────────►
              │            C ────────────────────►
              │                  │
              │                  ├── Wave 2 ── V ─►
              │                  └─          G ───►
              │                                │
              │                                └── Wave 3 ── I ──►
```

- **Wave 0 (2 parallel):** F is the Swift blocker; P is fully independent (Python-only). They run concurrently.
- **Wave 1 (2 parallel):** R and C run after Wave 0 merges (both F and P). R needs P for the `paused` row contract.
- **Wave 2 (2 parallel):** V and G run after R + C merge. V also consumes C; G is read-only against R.
- **Wave 3 (sequential):** I wires `OgmacApp` to the real scenes, ships the Homebrew cask, updates docs.

Wall-clock estimate: ≈ 4 dispatch rounds. Critical path: F → R → V → I (R is the longest single Wave 1 task because it carries fixture-heavy log-parser tests).

---

## Agent specs

### F — Foundation (Swift scaffold)

**Mission:** Stand up the Xcode project so every other Swift agent can `xcodebuild` and start writing tests.

**Owns:**
- `Ogmac.xcodeproj/` (project, scheme, build settings)
- `Ogmac/Info.plist` — `LSUIElement=true`, no `CFBundleIconFile`, bundle id `com.ogmac.app`
- `Ogmac/OgmacApp.swift` — `@main` entry with a placeholder `MenuBarExtra("ogmac", systemImage: "circle") { Text("loading") }` body. **I will modify this file in Wave 3** — sanctioned handoff, not a collision.
- `Ogmac/Assets.xcassets/AppIcon.appiconset/` (placeholder app icon — final art is out of scope)
- `OgmacTests/` empty target, hooked into the scheme
- Xcode build target: macOS 13.0+, Swift 5.9+
- **SPM dependencies pre-wired** (so Wave 1 agents don't need to touch `project.pbxproj`):
  - `GRDB.swift` ≥ 6.x — used by R for SQLite reads
  - `Yams` ≥ 5.x — used by R for YAML load/save

**Does NOT own:** any feature module, any view, any test of behavior, the IconStates asset catalog (V owns those).

**Depends on:** nothing.

**Blocks:** R, C, V, G, I.

**Done when:** `xcodebuild -project Ogmac.xcodeproj -scheme Ogmac build` succeeds; running the resulting `.app` shows a placeholder menu bar icon and no Dock icon; `OgmacTests` target runs zero tests cleanly.

---

### P — Python diff (pause + side fix)

**Mission:** Add the `paused` flag to the daemon and drop the dead `sync.interval_seconds` field. Independent of all Swift work.

**Owns:**
- `src/ogmac/state.py` — add `paused` boolean column to `run_state`, `is_paused`/`pause()`/`unpause()` methods mirroring the existing `is_disabled`/`disable()`/`enable()` shape
- `src/ogmac/cli.py` — add `pause` and `unpause` subcommands; insert `if state.is_paused: return 0` early-return in `_run_sync` (alongside the existing `state.is_disabled` check at lines 61–63)
- `src/ogmac/config.py` — remove `interval_seconds` from `SyncConfig`
- `docs/setup.md` — remove the `sync.interval_seconds` line from the example YAML and any prose that references it
- `docs/operations.md` — add a "Pause syncing" section documenting `ogmac pause` / `ogmac unpause`
- `tests/unit/test_state.py` — extend with `paused` flag tests (set/unset, default false, persistence across `State` reopen)
- `tests/unit/test_config.py` — assert `interval_seconds` is no longer accepted (extra-field rejection if model is strict, otherwise just verify it's gone from the schema)
- `tests/integration/test_pause_flow.py` (new) — `ogmac pause` → `ogmac sync` returns 0 with no Outlook/Google calls; `ogmac unpause` → `ogmac sync` runs normally

**Interface produced (consumed by Swift agents):**
- New CLI subcommands: `ogmac pause`, `ogmac unpause`
- New row in `run_state` table: `(key='paused', value='1'|'0')`

**Does NOT own:** any Swift file; the launchd plist; the install script; reconciler / google / outlook modules.

**Depends on:** nothing.

**Blocks:** C (commander invokes `pause`/`unpause`), R (StateReader reads the `paused` row).

**Done when:** All extended tests pass; `ogmac pause && ogmac sync && ogmac status` prints `last_success_at` unchanged; `ogmac unpause && ogmac sync` updates it; `Config.load` rejects (or ignores) `sync.interval_seconds` without error on legacy configs.

**Compatibility note:** Existing user configs may still contain `interval_seconds`. Decide between strict rejection (clean) or silent-drop (compatible). Spec is silent — pick silent-drop and log a one-line deprecation warning.

---

### R — Read adapters

**Mission:** Build the read-only data layer the views consume. Three small files, each with one responsibility.

**Owns:**
- `Ogmac/Models/StateSnapshot.swift` — `struct StateSnapshot { lastSuccessAt: Date?; consecutiveFailures: Int; disabled: Bool; paused: Bool; disableReason: String? }`
- `Ogmac/Models/SyncRun.swift` — `struct SyncRun { startedAt: Date; result: SyncResult; durationMs: Int?; counts: ReconcileCounts? }`; `enum SyncResult { case success, failure(reason: String) }`; `struct ReconcileCounts { create, update, delete, skip: Int }`
- `Ogmac/Models/ConfigDoc.swift` — Codable struct mirroring `~/.config/ogmac/config.yaml` shape (Connection / Sync / Privacy nested structs; Failure ignored on write to preserve user's value)
- `Ogmac/StateReader.swift` — opens `~/Library/Application Support/ogmac/state.db` read-only with SQLite C API or `GRDB.swift`; queries `run_state` rows; returns `StateSnapshot`
- `Ogmac/LogReader.swift` — reads `~/Library/Logs/ogmac/sync.log` and rotated copies (`.1` … `.10`); groups lines into `SyncRun` records using `sync.start` / `sync.success` / `sync.failure` / `reconcile` markers; returns the most recent N (default 50)
- `Ogmac/ConfigStore.swift` — loads `config.yaml` via `Yams`; saves via temp-file + `rename` for atomicity; never blocks on the main thread
- `OgmacTests/StateReaderTests.swift` — fixture sqlite databases (healthy / disabled / paused / failed)
- `OgmacTests/LogReaderTests.swift` — fixture `sync.log` files (clean run, failed run, partial run truncated mid-sync, rotated logs spanning files)
- `OgmacTests/ConfigStoreTests.swift` — round-trip (load → mutate → save → reload), atomicity (write fails partway → original intact), legacy field handling (`interval_seconds` ignored)
- `OgmacTests/Fixtures/state_*.sqlite` — generated once; checked in
- `OgmacTests/Fixtures/sync_log_*.txt`
- `OgmacTests/Fixtures/config_*.yaml`

**Interface produced:**
- `protocol StateReading { func snapshot() async throws -> StateSnapshot }`
- `protocol LogReading { func tail(maxRuns: Int) async throws -> [SyncRun] }`
- `protocol ConfigStoring { func load() throws -> ConfigDoc; func save(_ doc: ConfigDoc) throws }`

**Does NOT own:** any view, the OgmacRunner, anything that writes to `state.db`, anything that talks to a subprocess.

**Depends on:** F (project scaffold), P (the `paused` row in `run_state` — read by `StateReader.snapshot()`).

**Blocks:** V, G, I.

**Done when:** All three protocols have a default implementation; unit tests cover happy path + each failure mode listed above; tests pass under `xcodebuild test`.

**Library choice:** Use `GRDB.swift` for SQLite (cleaner than raw C API) and `Yams` for YAML. Both are SPM-installable, MIT-licensed, lightweight. R adds them to `Package.swift` / project SPM dependencies.

---

### C — Commander

**Mission:** Wrap `Process` invocations of the `ogmac` CLI. One file, one job: shell out and report.

**Owns:**
- `Ogmac/OgmacRunner.swift` — `class OgmacRunner` with: `binaryPath: URL?` resolver (PATH first, then `~/.local/share/ogmac/venv/bin/ogmac`); `func sync() async throws`; `func pause() async throws`; `func unpause() async throws`; `func resume() async throws`; `func reset(yes: Bool) async throws`; each method runs the CLI, captures stdout/stderr, throws if exit != 0
- `Ogmac/RunnerError.swift` — `enum RunnerError: Error { case binaryNotFound; case nonZeroExit(code: Int32, stderr: String) }`
- `OgmacTests/OgmacRunnerTests.swift` — uses a fake `ogmac` shim (a shell script the test creates in a temp dir, prepended to PATH) that echoes a known string and exits with controllable code; verifies path resolution preference, exit-code handling, stderr capture

**Interface produced:**
- `protocol OgmacCommanding { func sync() async throws; func pause() async throws; func unpause() async throws; func resume() async throws; func reset(yes: Bool) async throws; var binaryPath: URL? { get } }`

**Does NOT own:** any view, any data reader, anything that parses the daemon's output beyond exit code + stderr text.

**Depends on:** F (scaffold), P (so `ogmac pause`/`unpause` exist when integration testing — but unit tests use a fake shim, so P is not a hard prerequisite for C's unit tests).

**Blocks:** V (status panel's "Sync now" button), I.

**Done when:** All commands exercised against a fake shim; binary-not-found path returns `RunnerError.binaryNotFound`; `sync()` running against the real installed `ogmac` (manual smoke test) completes without throwing.

---

### V — Views (status + history)

**Mission:** Render the dropdown panel and the history sheet from the read adapters. Owns the icon-state derivation logic.

**Owns:**
- `Ogmac/IconState.swift` — `enum IconState: String { case healthy, warning, error, autoDisabled, paused, syncing, needsLogin }`; computed `systemImageName: String`; computed `tint: Color`
- `Ogmac/StatusController.swift` — `@MainActor class StatusController: ObservableObject` with `@Published var icon: IconState`, `@Published var summary: PanelSummary`; runs a polling loop (5s when panel open, 60s when closed); resolves icon state per the priority order in spec §Status (Syncing → Paused → Auto-disabled → Needs login → Error → Warning → Healthy); exposes a `triggerSync()` that flips `icon` to `.syncing` while `OgmacRunner.sync()` is in flight
- `Ogmac/PanelSummary.swift` — `struct PanelSummary { lastSyncRelative: String; nextSyncRelative: String; readBackend: String; writeBackend: String; lastRunCounts: ReconcileCounts? }`
- `Ogmac/MenuPanelView.swift` — SwiftUI view rendering the dropdown shown in spec §Status
- `Ogmac/HistoryView.swift` — SwiftUI sheet displaying the last 50 `SyncRun`s as a list (started-at, result chip, duration, counts)
- `Ogmac/Assets.xcassets/IconStates/` — SF-Symbol-based icon variants per state (or PNG fallbacks)
- `OgmacTests/StatusControllerTests.swift` — table-driven: every (snapshot, syncing-flag) combination → expected `IconState`; verify the priority order resolves correctly (e.g., paused beats error)
- `OgmacTests/PanelSummaryTests.swift` — relative-time formatting (`"2 min ago"`, `"in 13 min"`, `"never"`)

**Interface produced:**
- `MenuPanelView(controller: StatusController, runner: OgmacCommanding)` — embeds in MenuBarExtra
- `HistoryView(reader: LogReading)` — opens as a sheet
- `StatusController(stateReader: StateReading, logReader: LogReading, runner: OgmacCommanding)`

**Does NOT own:** Settings UI, the app entry point, the launchd plist, anything that writes config.

**Depends on:** F, R, C.

**Blocks:** I.

**Parallelizable with:** G (zero shared files; both consume R but read-only).

**Done when:** Unit tests for the icon-state state machine all pass; SwiftUI Previews render each state correctly; clicking "Sync now" in a manual smoke test triggers a real sync and the icon animates.

---

### G — Settings UI

**Mission:** Three tabs of form fields backed by `ConfigStore`, plus the "Launch at login" toggle.

**Owns:**
- `Ogmac/SettingsScene.swift` — `struct SettingsScene: Scene` composing the three tabs as `TabView`
- `Ogmac/SettingsConnectionTab.swift` — backend segmented control, source/target free-text fields, account fields, client-secret path field with file picker
- `Ogmac/SettingsSyncTab.swift` — past/future-window steppers, read-only schedule label, "Launch at login" toggle
- `Ogmac/SettingsPrivacyTab.swift` — three toggles + the locked attendees toggle with tooltip
- `Ogmac/LaunchAtLogin.swift` — thin wrapper around `SMAppService.mainApp` exposing `var isEnabled: Bool { get set }`
- `Ogmac/SettingsViewModel.swift` — `@MainActor class SettingsViewModel: ObservableObject` holding the in-memory `ConfigDoc` for editing; constructor takes a `ConfigStoring`; `func save()` calls `store.save(doc)`
- `OgmacTests/SettingsViewModelTests.swift` — load → mutate → save → assert atomic file write
- `OgmacTests/LaunchAtLoginTests.swift` — limited (SMAppService is hard to test without a signed app; assert getter/setter at minimum)

**Interface produced:**
- `SettingsScene(viewModel: SettingsViewModel)` — registered in the App body alongside `MenuBarExtra`

**Does NOT own:** anything in the dropdown panel or history view, anything that writes to `state.db` or the plist, the OgmacRunner.

**Depends on:** F, R (`ConfigStore`).

**Blocks:** I.

**Parallelizable with:** V.

**Done when:** Each tab renders all its fields; saving a change writes `config.yaml` atomically (verified by reading the temp-file + rename pattern); "Launch at login" toggle survives an app restart; switching read backend shows the inline note about `ogmac login microsoft`.

---

### I — Integrator + Packaging

**Mission:** Wire `OgmacApp` to the real scenes, ship the Homebrew cask, write the build script, update user-facing docs. Runs last because every other agent's interface must already exist.

**Owns:**
- `Ogmac/OgmacApp.swift` — **modify** F's placeholder body to compose `MenuBarExtra { MenuPanelView(controller, runner) }`, the `SettingsScene(viewModel)`, and a `Window("History") { HistoryView(reader) }` triggered from a NotificationCenter event
- `Ogmac/AppDeps.swift` — dependency container constructing concrete `StateReader`, `LogReader`, `ConfigStore`, `OgmacRunner`, `StatusController`, `SettingsViewModel` instances
- `Ogmac/FirstLaunchView.swift` — shown when `OgmacRunner.binaryPath == nil` or `ConfigStore.load()` throws; explains "Run `ogmac login` in Terminal" with a copy button
- `OgmacTests/AppLaunchTests.swift` — minimal smoke test that `AppDeps.shared` constructs without crashing
- `packaging/Casks/ogmac.rb` — Homebrew cask spec; `postflight` clears `com.apple.quarantine`
- `packaging/build_app.sh` — `xcodebuild archive` + `xcodebuild -exportArchive` producing `Ogmac.app`; output to `dist/Ogmac.app`
- `README.md` — add "Menu bar app" section under Quickstart with install via Homebrew cask
- `docs/operations.md` — already touched by P for pause/unpause; I adds a "Menu bar app" subsection covering Quit-vs-Pause distinction
- `docs/troubleshooting.md` — add "Menu bar app shows 'CLI not found'" entry

**Does NOT own:** any file owned by F/P/R/C/V/G. Imports them; modifies only `OgmacApp.swift` (sanctioned handoff from F). If a bug surfaces in a dependency during integration, route it back to that agent — I does not patch other agents' files.

**Depends on:** F, P, R, C, V, G — everyone.

**Blocks:** nothing (terminal).

**Done when:** `packaging/build_app.sh` produces a launchable `.app`; manual install of the cask on a clean machine results in a working menu bar icon, working Sync-now, working Pause, working Settings save round-trip; all 7 agents' tests still green together under `xcodebuild test` + `pytest`.

---

## File ownership map (collision-free)

```
Ogmac.xcodeproj/                                  F
Ogmac/Info.plist                                  F
Ogmac/Assets.xcassets/AppIcon.appiconset/         F
Ogmac/Assets.xcassets/IconStates/                 V
Ogmac/OgmacApp.swift                              F (initial) → I (final wiring)
Ogmac/AppDeps.swift                               I
Ogmac/FirstLaunchView.swift                       I
Ogmac/Models/StateSnapshot.swift                  R
Ogmac/Models/SyncRun.swift                        R
Ogmac/Models/ConfigDoc.swift                      R
Ogmac/Models/PanelSummary.swift                   V
Ogmac/StateReader.swift                           R
Ogmac/LogReader.swift                             R
Ogmac/ConfigStore.swift                           R
Ogmac/OgmacRunner.swift                           C
Ogmac/RunnerError.swift                           C
Ogmac/IconState.swift                             V
Ogmac/StatusController.swift                      V
Ogmac/MenuPanelView.swift                         V
Ogmac/HistoryView.swift                           V
Ogmac/SettingsScene.swift                         G
Ogmac/SettingsConnectionTab.swift                 G
Ogmac/SettingsSyncTab.swift                       G
Ogmac/SettingsPrivacyTab.swift                    G
Ogmac/SettingsViewModel.swift                     G
Ogmac/LaunchAtLogin.swift                         G
OgmacTests/StateReaderTests.swift                 R
OgmacTests/LogReaderTests.swift                   R
OgmacTests/ConfigStoreTests.swift                 R
OgmacTests/OgmacRunnerTests.swift                 C
OgmacTests/StatusControllerTests.swift            V
OgmacTests/PanelSummaryTests.swift                V
OgmacTests/SettingsViewModelTests.swift           G
OgmacTests/LaunchAtLoginTests.swift               G
OgmacTests/AppLaunchTests.swift                   I
OgmacTests/Fixtures/state_*.sqlite                R
OgmacTests/Fixtures/sync_log_*.txt                R
OgmacTests/Fixtures/config_*.yaml                 R
src/ogmac/state.py                                P  (modify)
src/ogmac/cli.py                                  P  (modify)
src/ogmac/config.py                               P  (modify)
docs/setup.md                                     P  (modify)
docs/operations.md                                P  (modify) → I (modify, add menu-bar section)
tests/unit/test_state.py                          P  (modify)
tests/unit/test_config.py                         P  (modify)
tests/integration/test_pause_flow.py              P
packaging/Casks/ogmac.rb                          I
packaging/build_app.sh                            I
README.md                                         I  (modify)
docs/troubleshooting.md                           I  (modify)
```

The only handoff is `OgmacApp.swift` (F → I) and `docs/operations.md` (P → I, additive section). All other files have a single owner.

---

## Dependency matrix

| Agent | Reads from |
|---|---|
| F | — |
| P | — |
| R | F (scaffold), P (`paused` row contract) |
| C | F |
| V | F, R, C |
| G | F, R |
| I | F, P, R, C, V, G |

**Critical path:** F → R → V → I. C runs alongside R in Wave 1; G runs alongside V in Wave 2; P runs alongside F in Wave 0 and only re-enters when C/R consume its outputs.

---

## Orchestrator responsibilities (you)

1. Dispatch F + P in parallel (Wave 0). Both must merge before Wave 1.
2. Dispatch R + C in parallel (Wave 1). Both must merge before Wave 2.
3. Dispatch V + G in parallel (Wave 2). Both must merge before Wave 3.
4. Dispatch I alone (Wave 3). Treat any cross-module bug surfaced here as a ticket back to the original owner — I does not patch other agents' files (the one exception is the sanctioned `OgmacApp.swift` rewrite).
5. Between waves, run the appropriate test suite (`xcodebuild test` for Swift waves, `pytest` after P, both at the end). A new wave does not start until the prior wave is green.
6. Code review per agent: check the interface they produced matches the contract listed under their "Interface produced" section. Anything beyond that contract is scope creep — push back.

---

## Out-of-scope guardrails (apply to all agents)

Mirrors spec "Non-goals (v0.1)". Reject any agent output that adds:

- In-app OAuth / Google login flow. First-launch points users to Terminal, period.
- Replacing `install.sh`. The separate installation rework is happening in parallel.
- Calendar pickers (free-text only in v0.1; defer `ogmac list-calendars` CLI to v0.2).
- Code signing or notarization scaffolding (unsigned + Homebrew cask only).
- Reboot-persistent pause via `launchctl disable`. The `paused` flag in `state.db` is the only pause mechanism.
- `failure.*` settings exposure in any tab.
- Push-notification refinement beyond the existing `notify_on_failure` behavior.
- "Syncing" icon state for launchd-driven (non-user-triggered) syncs.
- Schedule editing in the Settings UI (label is read-only; spec §Settings is explicit).
- Writes to `state.db` or the launchd plist from the Swift side. The Swift app reads only.
- Any `NSCalendarsUsageDescription` entitlement. EventKit reads stay in the Python daemon.
- A structured `runs` table in `state.db` (defer to v0.2 if log parsing becomes burdensome).
