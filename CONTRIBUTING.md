# Contributing to ogmac

Thanks for your interest! ogmac is a small, focused tool — patches that keep it that way are most welcome.

## Development setup

Requires macOS 12+ and Python 3.11+ (`brew install python@3.11`).

```bash
git clone https://github.com/razbahri/ogmac.git
cd ogmac
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running tests

The default test suite is hermetic — no network, no Keychain, no real EventKit:

```bash
pytest -q
```

Two integration tests are gated behind an env var because they hit real APIs:

```bash
OGMAC_LIVE=1 pytest tests/integration/
```

`test_google_live.py` requires a Google OAuth refresh token in Keychain (`ogmac login google`) and a calendar named `ogmac-test`. `test_graph_live.py` requires `read_method=microsoft_graph` and a refresh token from `ogmac login microsoft`.

## Linting & type checking

```bash
ruff check .
ruff format .
mypy src/ogmac
```

CI runs `ruff check` and `pytest` on macOS for Python 3.11, 3.12, and 3.13.

## Project layout

- `src/ogmac/` — package source
  - `cli.py` — entry point and sync orchestration
  - `outlook.py` — Microsoft Graph backend
  - `outlook_eventkit.py` — Apple Calendar / EventKit backend
  - `google.py` — Google Calendar API client
  - `auth.py` — Keychain token storage and OAuth flows
  - `reconciler.py` — pure diff logic between source and target events
  - `state.py` — local SQLite state (event map, run state)
- `tests/unit/` — pure-logic tests
- `tests/e2e/` — full-run tests with mocked external services
- `tests/integration/` — opt-in tests against real APIs
- `packaging/` — `install.sh` and the launchd plist
- `scripts/probe_eventkit.py` — dev helper to inspect EventKit calendar sources
- `docs/superpowers/specs/` — design spec

## Coding conventions

- Pure functions over classes where reasonable; keep side effects at the edges (CLI, network, filesystem).
- The reconciler must stay pure — all I/O happens in `cli.py`.
- Add a unit test for any new branch in the diff/reconcile logic.
- Follow the existing logging idiom: `event.kind key1=val1 key2=val2`.

## Submitting changes

1. Fork and branch from `main`.
2. Add tests for the change.
3. Run `pytest`, `ruff check`, and `mypy` locally.
4. Open a PR with a one-line summary and a short description of the why.

For larger changes, please open an issue first to align on direction.
