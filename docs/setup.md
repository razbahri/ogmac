# Setup

Setting up ogmac takes ~10 minutes once you've decided which backend to use. There are two — pick one and skip the other section.

## 1. Choose a backend

ogmac can read Outlook two ways. Pick one now — you'll write it into the config in step 5 (`outlook.read_method: apple_calendar` or `microsoft_graph`).

|  | `apple_calendar` *(default, recommended)* | `microsoft_graph` |
|---|---|---|
| **How it reads Outlook** | Via Apple's EventKit — same data Calendar.app shows | Direct calls to the Microsoft Graph API |
| **Auth flow** | Add Exchange in System Settings; macOS handles auth/refresh | OAuth via the public Graph CLI client; refresh token in Keychain |
| **Microsoft tenant friction** | None — bypasses third-party app gates entirely | **Requires admin consent** on the tenant; many corporates block it |
| **Calendar.app required** | Yes — events must be syncing in Calendar.app first | No |
| **Sync delay** | Inherits Calendar.app's (typically a few minutes) | Direct fetch — no intermediate cache |

> [!NOTE]
> **If your work tenant has Conditional Access or strict admin-consent policies, start with `apple_calendar`.** It's the only path that works without IT involvement.

## 2. Install ogmac

```bash
git clone https://github.com/razbahri/ogmac.git && cd ogmac
./packaging/install.sh
```

This:

- Creates a venv at `~/.local/share/ogmac/venv` (override with `OGMAC_VENV_DIR=...`).
- Installs the `ogmac` package and its `ogmac` CLI shim.
- Writes `~/Library/LaunchAgents/com.ogmac.sync.plist`.
- Bootstraps the launchd job (15-minute schedule, runs at login).

> [!IMPORTANT]
> Requires **macOS 12+** and **Python 3.11+** (`brew install python@3.11`).

## 3a. Set up `apple_calendar` (recommended)

### Add Exchange to macOS

1. Open **System Settings → Internet Accounts → Add Account…**
2. Choose **Microsoft Exchange**.
3. Enter your name and work email, click **Sign In** → **Sign In** (Microsoft).
4. Complete the Microsoft sign-in (password + MFA, per your tenant).
5. When asked which apps should use this account, **enable Calendars**.
6. Click **Done**.
7. Open **Calendar.app** and confirm the new account appears in the sidebar with your work calendars under it.

> [!WARNING]
> Wait until events actually populate in Calendar.app before running ogmac. Initial Exchange sync can take from seconds to several minutes — sometimes longer on tenants with Conditional Access.

### Grant ogmac access to Calendars

The first sync will trigger a macOS permission prompt for the Python interpreter. Click **OK**.

If you missed or denied it: **System Settings → Privacy & Security → Calendars** → enable `~/.local/share/ogmac/venv/bin/python`.

To verify EventKit access independently:

```bash
~/.local/share/ogmac/venv/bin/python scripts/probe_eventkit.py
```

The probe lists calendar sources, individual calendars, and a sample of upcoming events. If it returns events, ogmac will too.

## 3b. Set up `microsoft_graph` (alternative)

Skip the Exchange-in-System-Settings step entirely. After install, run:

```bash
ogmac login microsoft
```

A browser opens to the Microsoft sign-in page. Complete OAuth; the refresh token lands in Keychain (`ogmac.microsoft` service).

> [!CAUTION]
> If you see **"Approval required"** or **"Need admin approval"**, your tenant gates the public Graph CLI client. Either request approval through your IT portal, or switch `read_method` to `apple_calendar` and skip this entirely.

## 4. Set up Google (both paths)

### Create the OAuth client

1. Open [console.cloud.google.com](https://console.cloud.google.com) and create or select a project.
2. **APIs & Services → Library** → search "Google Calendar API" → **Enable**.
3. **APIs & Services → OAuth consent screen** → User type **External** → fill app name, user support email, developer email. Add your Gmail address as a **test user**. Leave the app in **Testing** status.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID** → Application type **Desktop app** → name it `ogmac` → Create.
5. Download the JSON. Save it as `~/.config/ogmac/client_secret.json`.

> [!TIP]
> Enable the Calendar API **before** creating the OAuth client. Otherwise the first sync fails with `accessNotConfigured`.

### Find the target Google Calendar ID

[Google Calendar](https://calendar.google.com) → Settings → pick (or create) a dedicated calendar (e.g. "Work (synced)") → scroll to **Integrate calendar** → copy the **Calendar ID** (looks like `abc123…@group.calendar.google.com`).

> [!IMPORTANT]
> Use a **dedicated calendar**. ogmac will create, update, and delete events on it. Don't point it at your primary calendar — the safety filter (`ogmac_owned=1`) prevents collisions, but a dedicated calendar makes the boundary visible.

## 5. Write the config

Create `~/.config/ogmac/config.yaml`:

```yaml
outlook:
  account: you@example.com          # apple_calendar: informational; microsoft_graph: UPN used as Keychain key
  source_calendar: default          # see "Field semantics" below
  read_method: apple_calendar       # or: microsoft_graph

google:
  account: you@gmail.com            # used as Keychain account key
  client_secret_path: ~/.config/ogmac/client_secret.json
  target_calendar_id: <google_calendar_id>

sync:
  window_past_days: 1
  window_future_days: 30

privacy:
  copy_subject: true
  copy_location: true
  copy_body: true
  copy_attendees: false             # locked to false; validation rejects true

failure:
  max_consecutive_before_disable: 5
  notify_on_failure: true
```

### Field semantics by backend

| Field | `apple_calendar` | `microsoft_graph` |
|---|---|---|
| `outlook.account` | Informational only | UPN — used as Keychain account key |
| `outlook.source_calendar` | `default` (first Exchange calendar) or an EKCalendar identifier (run `scripts/probe_eventkit.py` to list) | `default` (user's primary) or a Graph calendar ID |

## 6. Login & verify

```bash
ogmac login            # logs in whatever your read_method needs, plus Google
ogmac sync             # one manual sync to verify
ogmac status           # exits 0 if last success was within 24h
```

`ogmac login` is read-method-aware:

- With `apple_calendar`: logs in to Google only.
- With `microsoft_graph`: logs in to both Microsoft and Google.

You can also target one provider explicitly: `ogmac login google` or `ogmac login microsoft`.

---

Once `ogmac sync` and `ogmac status` are happy, launchd takes over. Move on to [Operations](operations.md).
