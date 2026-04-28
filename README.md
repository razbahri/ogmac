<div align="center">

<img src="docs/assets/hero.png" alt="ogmac — Outlook → Google Calendar mirror for macOS" width="820">

[![tests](https://github.com/razbahri/ogmac/actions/workflows/test.yml/badge.svg)](https://github.com/razbahri/ogmac/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform: macOS 12+](https://img.shields.io/badge/platform-macOS%2012%2B-lightgrey.svg)](https://support.apple.com/macos)
[![Status: Beta](https://img.shields.io/badge/status-beta-orange.svg)](#status)

</div>

---

ogmac runs every 15 minutes via macOS `launchd` and mirrors your work Outlook calendar into a dedicated Google Calendar — so your meetings show up wherever you (and the people in your life) actually look. No SaaS bridge, no shared servers, no third-party access tokens. Tokens live in **macOS Keychain**; events go straight to **`googleapis.com`**.

> [!TIP]
> Two interchangeable backends. Use **Apple Calendar (EventKit)** when your tenant blocks third-party Microsoft Graph apps — no Microsoft OAuth required. Use **Microsoft Graph** when you don't want Exchange wired into the OS. Switch any time by editing one config line.

## Quickstart

```bash
git clone https://github.com/razbahri/ogmac.git && cd ogmac
./packaging/install.sh
```

Then:

1. Configure `~/.config/ogmac/config.yaml` — see [docs/setup.md](docs/setup.md).
2. Drop your Google OAuth client at `~/.config/ogmac/client_secret.json`.
3. `ogmac login` and `ogmac sync` to verify.

That's it. From then on, launchd runs `ogmac sync` every 15 minutes in the background.

## How it works

```mermaid
flowchart LR
    O[("Outlook<br/>M365 / Exchange")] --> EK[Apple EventKit]
    O --> MG[Microsoft Graph]
    EK -->|read_method:<br/>apple_calendar| OG{{"ogmac<br/>launchd · every 15m"}}
    MG -->|read_method:<br/>microsoft_graph| OG
    OG -->|owned events only| GC[("Google Calendar<br/>dedicated calendar")]

    classDef src fill:#0078D4,color:#fff,stroke:#005A9E
    classDef sink fill:#34A853,color:#fff,stroke:#188038
    classDef ogmac fill:#1f1f1f,color:#fff,stroke:#888
    class O src
    class GC sink
    class OG ogmac
```

ogmac stamps every event it creates with an `ogmac_owned=1` marker and only ever sees its own events on the Google side. User-created events on the target calendar are invisible to it and never touched.

## Documentation

| | |
|---|---|
| 🛠 **[Setup](docs/setup.md)** | Pick a backend, add Exchange to System Settings, create the Google OAuth client, write the config. |
| ⚙️ **[Operations](docs/operations.md)** | `status`, `resume`, `reset`, stop / disable / uninstall, logs. |
| 🧩 **[Architecture](docs/architecture.md)** | Field mapping, identity markers, reconciliation model. |
| 🩺 **[Troubleshooting](docs/troubleshooting.md)** | Permission denials, OAuth dead-ends, launchd silence, token expiry. |
| 🤝 **[Contributing](CONTRIBUTING.md)** | Dev setup, test suite, project layout. |

## Privacy

ogmac copies event **title, time, location, body, availability, and all-day flag** to your Google Calendar. **Attendees are never copied.** Outbound traffic is limited to:

- `googleapis.com` (always)
- `graph.microsoft.com` (only when `read_method: microsoft_graph`)

Refresh tokens are stored exclusively in **macOS Keychain**; nothing sensitive is written to disk in plaintext.

## Status

ogmac is **beta** — it works on the author's machine and others, but the API surface (config schema, CLI flags) may shift before 1.0. Pin a tag if you depend on it. Bug reports welcome via [Issues](https://github.com/razbahri/ogmac/issues).

## Out of scope

Two-way sync · multiple calendar pairs · categories / colors / reminders · attachments · GUI · multi-user packaging · auto-update · Graph webhooks / push notifications · classic Outlook AppleScript · EWS fallback.

## License

[MIT](LICENSE) © ogmac contributors
