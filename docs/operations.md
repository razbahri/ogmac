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
