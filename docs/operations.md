# Operations

Day-to-day commands and lifecycle management.

## Status & control

### `ogmac status`

Prints `last_success_at`, `consecutive_failures`, and `disabled` state. Exits **0** if not disabled and last success was within 24 hours; **1** otherwise.

```bash
ogmac status
```

### `ogmac sync`

One manual sync. Useful for verifying setup, testing config changes, or after `ogmac resume`.

```bash
ogmac sync
```

### `ogmac resume`

Clears the auto-disable flag, resets the failure counter, and runs an immediate sync. Use after fixing whatever caused [auto-disable](#auto-disable).

```bash
ogmac resume
```

### Pause syncing

`ogmac pause` sets a soft pause flag that causes `ogmac sync` to return immediately without contacting Outlook or Google. Use it when you need to suppress sync temporarily without triggering the auto-disable logic.

```bash
ogmac pause
ogmac unpause
```

- `ogmac pause` — set the pause flag; subsequent syncs are skipped with `sync.skipped reason=paused` in the log.
- `ogmac unpause` — clear the flag; the next scheduled or manual sync runs normally.

The flag survives restarts (it is persisted in `~/Library/Application Support/ogmac/state.db`). The auto-disable counter is unaffected — skipped syncs do not increment `consecutive_failures`.

### `ogmac reset`

Deletes **all ogmac-owned events** from the target Google calendar and wipes local state (event map, run state, failure counter). Tokens are preserved.

```bash
ogmac reset           # interactive confirmation
ogmac reset --yes     # scripted
```

> [!WARNING]
> `reset` is destructive on the Google side, but it only touches events stamped with `ogmac_owned=1`. User-created events on the same calendar are untouched. Still — back up if you care.

Use `reset` after a sync-shape change rolls out (e.g., availability handling, all-day formatting) to backfill existing events on the next sync.

## Auto-disable

If sync fails `failure.max_consecutive_before_disable` times in a row (default: **5**), ogmac flips the `disabled` flag and stops trying. A macOS notification fires (if `failure.notify_on_failure: true`).

To recover:

1. Read `~/Library/Logs/ogmac/sync.log` for the actual error.
2. Fix the root cause (re-login, fix config, restore Calendar.app sync, etc.).
3. Run `ogmac resume`.

## Stop, disable, or uninstall

Three levels — pick the one that matches your intent:

### Stop until next login

Removes the job from the running launchd domain. Reloads automatically next time you log in (because the plist is still in `~/Library/LaunchAgents`).

```bash
launchctl bootout gui/$UID/com.ogmac.sync
```

### Disable across reboots

Persists in launchd's override database. The plist stays in place, but launchd refuses to load it until re-enabled — even after a reboot.

```bash
launchctl disable gui/$UID/com.ogmac.sync
launchctl bootout gui/$UID/com.ogmac.sync   # stop the currently loaded copy
```

Re-enable later:

```bash
launchctl enable gui/$UID/com.ogmac.sync
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.ogmac.sync.plist
```

### Uninstall completely

```bash
launchctl bootout gui/$UID/com.ogmac.sync
rm ~/Library/LaunchAgents/com.ogmac.sync.plist
rm -rf ~/.local/share/ogmac/venv
```

This leaves your config, local state, logs, and Keychain tokens intact.

To wipe everything:

```bash
rm -rf ~/.config/ogmac \
       ~/Library/Application\ Support/ogmac \
       ~/Library/Logs/ogmac
```

Keychain entries (`ogmac.google`, `ogmac.microsoft`) survive — delete them manually in **Keychain Access** if desired.

## Logs

| File | Contents |
|---|---|
| `~/Library/Logs/ogmac/sync.log` | Structured sync log. INFO by default; set `OGMAC_DEBUG=1` for DEBUG. |
| `~/Library/Logs/ogmac/launchd.out.log` | launchd stdout |
| `~/Library/Logs/ogmac/launchd.err.log` | launchd stderr — Python crash traces land here |

Rotation: **10 files × 1 MB each**.

### Tailing live

```bash
tail -f ~/Library/Logs/ogmac/sync.log
```

### Debug a single run

```bash
OGMAC_DEBUG=1 ogmac sync 2>&1 | tail -200
```

## Verifying the schedule

```bash
launchctl print "gui/$UID/com.ogmac.sync"
```

Look for:

- `state = waiting` — loaded and waiting for next interval ✅
- `state = running` — sync in progress
- `state = not running` + `last exit code = 0` — last sync succeeded
- `last exit code = 1` — last sync failed; check `sync.log`

If the job doesn't appear at all, re-run `./packaging/install.sh`.

## Menu bar app

`Ogmac.app` is a companion menu bar app that surfaces sync status, settings, and run history without requiring terminal access. It does **not** replace the launchd daemon — the two run independently.

### Quit vs. Pause

| Action | Effect on sync |
|---|---|
| **Quit ogmac** (menu item) | Terminates the menu bar app process. The launchd job continues to fire on schedule — sync keeps running. |
| **Pause** (menu item or `ogmac pause`) | Sets a flag in `~/Library/Application Support/ogmac/state.db`. Every subsequent sync (whether triggered by launchd or `ogmac sync`) returns immediately with `sync.skipped reason=paused`. The flag persists across reboots. |
| **Resume** (menu item or `ogmac unpause`) | Clears the pause flag. The next scheduled sync runs normally. |

Use Quit when you no longer want the icon visible. Use Pause when you want to suppress sync activity (e.g., during travel or when on a metered connection) without disabling launchd.

### How the panel stays fresh

The app does **not** poll on a timer. It installs a `DispatchSource` file-system watcher on `~/Library/Application Support/ogmac/state.db`. The daemon writes that file at the end of each sync (the SQLite connection closes, triggering a WAL checkpoint). The watcher fires within ~200 ms and the panel refreshes — independent of how long the sync took. Long syncs (>1 min) no longer race with a 60 s poll.

The panel additionally refreshes:
- Once at app startup.
- On each `MenuPanelView.onAppear` (when you click the menu bar icon).
- After a `Sync now` click — `triggerSync` awaits the `ogmac sync` Process and refreshes when it exits.

If `state.db` doesn't exist yet (no sync has ever run), the app falls back to a 30 s timer that retries the watcher and refreshes opportunistically until the file appears.

### History view filter

The History sheet hides the network-change-driven no-op syncs that fire every ~2 min from the launchd plist's `LaunchEvents` block (see `packaging/com.ogmac.sync.plist`). A run is shown if any of:

- `create + update + delete > 0` (real work happened), or
- the run failed (always interesting), or
- the run started within 90 s of `:00`/`:15`/`:30`/`:45` (the scheduled ticks).

### Launch at login

Enable in **Settings → Sync → Launch at login**. This registers `Ogmac.app` with `SMAppService` independently of the launchd sync job.

### Diagnostic log

The app writes a per-event structured log at `~/Library/Logs/ogmac/menubar.log`, distinct from the daemon's `sync.log`. Tail it to see refresh ticks, file-watcher events, and reader errors:

```bash
tail -f ~/Library/Logs/ogmac/menubar.log
```

The file is plain ISO-8601-prefixed text and is append-only (no built-in rotation in v0.2). Delete it to reset.
