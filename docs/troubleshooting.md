# Troubleshooting

Symptoms grouped by where they originate.

## Apple Calendar / EventKit (`read_method: apple_calendar`)

### `Calendar access denied`

EventKit was denied. Open **System Settings → Privacy & Security → Calendars** → enable the Python interpreter that runs ogmac (`~/.local/share/ogmac/venv/bin/python`).

### `No Exchange primary calendar found`

Either the Exchange account isn't configured in **System Settings → Internet Accounts**, or Calendar.app hasn't finished its initial sync. Open Calendar.app, wait until events appear under the Exchange account in the sidebar, then retry.

### Events appear in Calendar.app but not in ogmac

Run the probe to see what EventKit reports:

```bash
~/.local/share/ogmac/venv/bin/python scripts/probe_eventkit.py
```

If the probe lists your calendars but no events: the window in `sync.window_past_days` / `window_future_days` may not cover the events you're looking at. Bump the future window and retry.

### macOS doesn't show the permission prompt

The prompt only fires once per binary identity. If you denied it, macOS won't ask again — you have to enable it manually in **System Settings → Privacy & Security → Calendars**.

## Microsoft Graph (`read_method: microsoft_graph`)

### `Need admin approval` / `AADSTS65001` / "Approval required"

Your tenant gates the public Graph CLI client behind admin consent. Two options:

1. Request approval through your IT portal (may take days/weeks/never).
2. Switch to `read_method: apple_calendar` — it doesn't require any Microsoft OAuth.

### `InvalidAuthenticationToken`

Refresh token in Keychain is stale or invalid. Re-login:

```bash
ogmac login microsoft
```

### Microsoft login succeeded but events are wrong

Confirm `outlook.source_calendar` matches the calendar you actually want. `default` reads the user's primary; otherwise pass a Graph calendar ID.

## Google

### `accessNotConfigured`

Google Calendar API isn't enabled in your Cloud project.
**Cloud Console → APIs & Services → Library → Google Calendar API → Enable.**

### `TokenRefreshError: No Google credentials in Keychain`

First-time setup, or Keychain was cleared. Run:

```bash
ogmac login google
```

### `calendarNotFound`

`google.target_calendar_id` doesn't match a calendar you own. Recheck **Google Calendar → Settings → Integrate calendar → Calendar ID**.

### "Access blocked: ogmac has not completed verification"

Add your Gmail to **Test users** on the OAuth consent screen. The app can stay in **Testing** status indefinitely for personal use — no Google verification required.

### Refresh token expired after 7 days

Apps in **Testing** mode get refresh tokens that expire after 7 days. Two fixes:

1. Run `ogmac login google` again (quick, but you'll repeat it weekly).
2. Move the OAuth consent screen to **In production** — for the `calendar.events` scope on your own account, no Google verification is required.

## launchd / scheduling

### `ogmac auto-disabled` notification

Five consecutive failures occurred. Check `ogmac status` and `~/Library/Logs/ogmac/sync.log` for the underlying error. Fix the root cause, then:

```bash
ogmac resume
```

### launchd not firing

```bash
launchctl print "gui/$UID/com.ogmac.sync"
```

If the job isn't listed, re-run `./packaging/install.sh`. If it's listed but `last exit code != 0`, check `launchd.err.log` for a Python traceback.

### Job runs but never makes progress

Check `~/Library/Logs/ogmac/launchd.err.log` for an unhandled exception (these don't go to `sync.log`).

## Sync output looks wrong

### All-day OOO event takes the whole day instead of a thin strip

Older syncs (before all-day support landed) wrote all-day events as 24-hour timed blocks. Backfill:

```bash
ogmac reset --yes && ogmac sync
```

### Old events still in Google after I deleted them in Outlook

The reconciliation window is `[now - window_past_days, now + window_future_days]`. Events outside it aren't tracked anymore. Either widen the window in config, or `ogmac reset --yes && ogmac sync`.

### Tentative meetings show as busy

Expected. Outlook's `Tentative` maps to Google's `transparency: opaque` (busy). Google has no native "tentative" transparency state. If you'd rather Tentative be free, edit `src/ogmac/google.py` and rebuild.

## Permission / Keychain

### macOS keeps prompting for Keychain access on every sync

Click **Always Allow** when prompted. If it keeps asking: open **Keychain Access** → search `ogmac` → for each item, **Get Info → Access Control → Always allow access by these applications** → add the Python binary.

### Lost a Keychain entry

Just re-login:

```bash
ogmac login google
ogmac login microsoft   # only if read_method: microsoft_graph
```

## Menu bar app

### Menu bar app shows "CLI not found" (FirstLaunchView)

The app checked for `ogmac` on `PATH` and at the venv fallback path (`~/.local/share/ogmac/venv/bin/ogmac`) and found neither. This happens on a clean machine before the CLI is installed, or after moving/deleting the venv.

**Fix:** run the installer, which installs the venv and registers the CLI:

```bash
./packaging/install.sh
```

Then quit and reopen `Ogmac.app`. If the app still shows the setup screen after the CLI is installed, confirm the binary is on the PATH that GUI apps see:

```bash
launchctl asuser $UID /usr/bin/env which ogmac
```

If blank, add the install location to your shell profile and re-login.

### Menu bar icon doesn't update

The app uses a file-system watcher on `~/Library/Application Support/ogmac/state.db` rather than a timer. Two cases:

1. **`state.db` doesn't exist yet** — happens on a clean machine before the first sync. The app falls back to a 30 s retry timer; once the daemon runs once, the watcher takes over. Force it with `ogmac sync`.
2. **The watcher silently isn't firing** — check `~/Library/Logs/ogmac/menubar.log` for `StateFileWatcher started fd=...` and subsequent `StateFileWatcher event` lines. If you see `started` but no events, the daemon isn't actually writing. Verify with `ls -la ~/Library/Application\ Support/ogmac/` and check the file mtime.

### History is empty even though `sync.log` has runs

The History view filters out the no-op syncs that fire every ~2 min from the plist's `NetworkChange` LaunchEvent (see `packaging/com.ogmac.sync.plist`). Only runs that did real work, failed, or landed near `:00`/`:15`/`:30`/`:45` are shown. If you've had a quiet hour and no scheduled ticks have happened yet, the list will be empty — that's expected.

### Settings changes don't persist

The settings pane writes to `~/.config/ogmac/config.yaml` on every field change (atomic temp-file + rename). If saves silently don't take effect, check `~/Library/Logs/ogmac/menubar.log` for ConfigStore errors. Common causes: the config directory doesn't exist yet (run `ogmac login` once to create it), or the file is owned by another user.

### Settings window doesn't appear

`Ogmac.app` runs as `LSUIElement=true` (no Dock icon), which means opening a window doesn't auto-activate the app. The Settings window is opened with an explicit `NSApp.activate(ignoringOtherApps: true)` in v0.2 — if it's still not coming to front, look behind your other windows or try `Cmd-Tab` and select **ogmac**.

## Still stuck?

Open an [Issue](https://github.com/razbahri/ogmac/issues) with:

- `ogmac --version` (or `pip show ogmac | grep Version`)
- macOS version
- The `read_method` from your config
- Last 100 lines of `sync.log` (redact emails, calendar IDs, event titles)
