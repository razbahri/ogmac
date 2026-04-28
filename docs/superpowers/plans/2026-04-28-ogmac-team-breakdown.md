# ogmac — Agent Team Breakdown

**Source spec:** `docs/superpowers/specs/2026-04-28-ogmac-design.md`
**Date:** 2026-04-28
**Purpose:** How to parallelize ogmac v1 across a team of subagents — roles, file ownership, dependencies, and execution waves.

---

## Headcount

**7 specialist agents + 1 orchestrator (you).**

Decomposition principle: split by *responsibility boundary*, not by file count. Each agent owns one cohesive concern with a clean interface to the rest. Pure / I/O / wiring layers are kept separate so the pure layer can be TDD'd in isolation and the I/O layers can be mocked independently.

| ID | Role | Layer |
|---|---|---|
| F | Foundation | scaffolding |
| R | Reconciler | pure core |
| D | Data + Config | persistence |
| A | Auth + Infra Utilities | cross-cutting |
| O | Outlook Boundary | I/O |
| G | Google Boundary | I/O |
| I | Integrator + Packaging | wiring + ops |

---

## Execution waves

```
Wave 0 ─── F ──────────────────────────────────────────────────►
                │
                ├── Wave 1 ── R ────────────────────────────────►
                │            D ────────────────────────────────►
                │            A ──┐
                │                │
                │                ├── Wave 2 ── O ───────────────►
                │                └──          G ───────────────►
                │                                         │
                │                                         └── Wave 3 ── I ──►
```

- **Wave 0 (sequential):** F is the blocker. Everyone reads `models.py` and depends on the project skeleton existing.
- **Wave 1 (3 parallel):** R, D, A run concurrently. None of them touch each other's files.
- **Wave 2 (2 parallel):** O and G run concurrently after A is merged (both consume `auth.py`).
- **Wave 3 (sequential):** I wires everything together; runs alone last.

Wall-clock estimate: ≈ 4 dispatch rounds (one per wave). R is the longest single critical path inside Wave 1 because it's the one module specified as test-first across the full diff matrix.

---

## Agent specs

### F — Foundation

**Mission:** Stand up the project so every other agent can `pip install -e .` and start writing tests on Python 3.11.

**Owns:**
- `pyproject.toml` (PEP 621, deps from spec §5)
- `.gitignore`
- `.python-version` (`3.11`)
- `src/ogmac/__init__.py`
- `src/ogmac/__main__.py` (stub: `from ogmac.cli import main; main()`)
- `src/ogmac/models.py` — `SourceEvent`, `TargetEvent`, `Action` (frozen dataclasses per §2)
- `tests/__init__.py`, `tests/unit/__init__.py` (skeleton dirs only)

**Does NOT own:** any logic file, any test of behavior.

**Depends on:** nothing.

**Blocks:** all other agents.

**Done when:** `python -m pytest` runs zero tests cleanly; `from ogmac.models import SourceEvent, TargetEvent, Action` works.

---

### R — Reconciler (pure core)

**Mission:** Implement the diff matrix from spec §2 as a pure function. Test-first, table-driven.

**Owns:**
- `src/ogmac/reconciler.py`
- `tests/unit/test_reconciler.py`

**Interface produced:** `def reconcile(sources: list[SourceEvent], targets: list[TargetEvent]) -> list[Action]`

**Does NOT own:** anything that does I/O, anything that touches SQLite, anything that calls Graph or Google.

**Test coverage required (from spec §5):**
- source-only → CREATE
- target-only → DELETE
- both, no change → SKIP
- both, source modified → UPDATE
- source cancelled occurrence → DELETE
- source moved out of window → DELETE (same path as missing)
- target without `ogmac_owned` marker (assert reconciler never sees it — caller filters)
- duplicate adoption (target with marker but no DB row → UPDATE not CREATE)

**Depends on:** F (for `models.py`).

**Blocks:** I (integrator imports `reconcile`).

---

### D — Data + Config

**Mission:** Own everything that reads from disk or persists to disk except tokens. State DB and YAML config live together because they share the "validated structured local data" concern.

**Owns:**
- `src/ogmac/state.py` — SQLite wrapper, schema bootstrap, `event_map` + `run_state` tables (spec §3)
- `src/ogmac/config.py` — pydantic models, YAML load, `copy_attendees=true` rejection
- `tests/unit/test_state.py`
- `tests/unit/test_config.py`

**Interface produced:**
- `class State` — `get/put/delete event_map row`, `get/set run_state key`, `consecutive_failures`, `disabled`
- `class Config` — pydantic `BaseModel`, `Config.load(path) -> Config`

**Does NOT own:** Keychain access (that's A), token JSON, anything HTTP.

**Depends on:** F.

**Blocks:** I, A (auth reads config for account names + client_secret_path).

---

### A — Auth + Infra Utilities

**Mission:** Cross-cutting infrastructure that doesn't fit cleanly into a domain layer: OAuth + Keychain, native notifications, log setup. Grouped because all three are "host integration" concerns and none is large enough to warrant its own agent.

**Owns:**
- `src/ogmac/auth.py` — MSAL + google-auth flows, Keychain via `keyring`, silent refresh, `ogmac login` flow
- `src/ogmac/notify.py` — `osascript` wrapper, banner + sticky alert
- `src/ogmac/logging_setup.py` — `RotatingFileHandler` at `~/Library/Logs/ogmac/sync.log`, format per spec §4
- `tests/unit/test_auth.py` (mocked keyring + mocked MSAL/google-auth)

**Interface produced:**
- `def get_graph_token() -> str`, `def get_google_credentials() -> Credentials`
- `def login_microsoft(cfg)`, `def login_google(cfg)`
- `def notify(title, body, sticky=False)`
- `def setup_logging(debug: bool = False)`

**Depends on:** F, D (config for account/client_secret paths).

**Blocks:** O, G (both call `get_*_token`), I (calls notify + setup_logging).

---

### O — Outlook Boundary

**Mission:** Read events from Microsoft Graph and normalize them into `SourceEvent`. Nothing else.

**Owns:**
- `src/ogmac/outlook.py` — `calendarView` query, pagination via `@odata.nextLink`, retry on 429/5xx, normalization
- `tests/unit/test_normalization.py` — Graph JSON fixture → `SourceEvent`
- `tests/integration/test_graph_live.py` — gated by `OGMAC_LIVE=1`
- `tests/fixtures/graph_calendarview_page.json`
- `tests/fixtures/graph_recurring_expanded.json`

**Interface produced:** `def fetch_source_events(token: str, start: datetime, end: datetime) -> list[SourceEvent]`

**Does NOT own:** any Google call, any state write, anything that decides what to do with the events.

**Depends on:** F, A.

**Blocks:** I.

**Parallelizable with:** G (zero shared files).

---

### G — Google Boundary

**Mission:** Read existing ogmac-owned events from Google and apply CREATE/UPDATE/DELETE actions. Owns the duplicate-adoption query for crash recovery (spec §2 idempotency).

**Owns:**
- `src/ogmac/google.py` — `events.list` with `privateExtendedProperty=ogmac_owned=1`, `events.insert/update/delete`, duplicate-adoption lookup, retry on 429/5xx
- `tests/integration/test_google_live.py` — gated by `OGMAC_LIVE=1`
- `tests/fixtures/google_events_list.json`

**Interface produced:**
- `def fetch_target_events(creds, calendar_id, start, end) -> list[TargetEvent]`
- `def apply_action(creds, calendar_id, action: Action) -> str | None` (returns google_id for CREATE)
- `def find_orphan_by_instance_id(creds, calendar_id, instance_id) -> str | None`

**Does NOT own:** any Outlook call, any reconciliation, anything in `state.db`.

**Depends on:** F, A.

**Blocks:** I.

**Parallelizable with:** O (zero shared files).

---

### I — Integrator + Packaging

**Mission:** Wire all six modules into the `sync / login / status / resume / reset` flow, write the e2e test, ship the launchd integration and installer. Runs last because every other agent's interface must already exist.

**Owns:**
- `src/ogmac/cli.py` — argparse, subcommands, the orchestration loop from spec §1, failure-counter logic from spec §4
- `tests/e2e/test_full_run.py` — both APIs mocked, real SQLite, real `cli.main(["sync"])`
- `packaging/com.ogmac.sync.plist` — verbatim from spec §4
- `packaging/install.sh` — venv creation, `pip install`, plist install, `launchctl bootstrap`
- `README.md` — install, login, troubleshooting

**Does NOT own:** any module owned by F/R/D/A/O/G. Imports them; does not modify them. If a bug surfaces in a dependency during integration, route it back to that agent.

**Depends on:** F, R, D, A, O, G — everyone.

**Blocks:** nothing (terminal).

---

## File ownership map (collision-free)

```
pyproject.toml                                    F
.gitignore                                        F
.python-version                                   F
README.md                                         I
src/ogmac/__init__.py                             F
src/ogmac/__main__.py                             F
src/ogmac/models.py                               F
src/ogmac/cli.py                                  I
src/ogmac/config.py                               D
src/ogmac/state.py                                D
src/ogmac/auth.py                                 A
src/ogmac/notify.py                               A
src/ogmac/logging_setup.py                        A
src/ogmac/outlook.py                              O
src/ogmac/google.py                               G
src/ogmac/reconciler.py                           R
tests/unit/test_reconciler.py                     R
tests/unit/test_state.py                          D
tests/unit/test_config.py                         D
tests/unit/test_auth.py                           A
tests/unit/test_normalization.py                  O
tests/integration/test_graph_live.py              O
tests/integration/test_google_live.py             G
tests/e2e/test_full_run.py                        I
tests/fixtures/graph_calendarview_page.json       O
tests/fixtures/graph_recurring_expanded.json      O
tests/fixtures/google_events_list.json            G
packaging/com.ogmac.sync.plist                I
packaging/install.sh                              I
```

No file appears under two owners. Every agent's deliverables are defined by paths, not by descriptions, so handoff is mechanical.

---

## Dependency matrix

| Agent | Reads from |
|---|---|
| F | — |
| R | F (`models`) |
| D | F |
| A | F, D (`config`) |
| O | F (`models`), A (`get_graph_token`) |
| G | F (`models`), A (`get_google_credentials`) |
| I | F, R, D, A, O, G |

**Critical path:** F → A → (O ∥ G) → I. R and D sit off the critical path; they finish during the A → O/G window without delaying anyone.

---

## Orchestrator responsibilities (you)

1. Dispatch F first; merge before fanning out.
2. Dispatch R, D, A in parallel after F merges. Three concurrent subagents.
3. Hold I until A merges. Dispatch O and G in parallel.
4. Dispatch I once all six are merged. Treat any cross-module bug surfaced here as a ticket back to the original owner — I does not patch other agents' files.
5. Between waves, re-run the full test suite. A new agent should not start until the prior wave is green.
6. Code review per agent: check the interface they produced matches the contract listed under their "Interface produced" section above. Anything beyond that contract is scope creep — push back.

---

## Out-of-scope guardrails (apply to all agents)

Mirrors spec "Out of scope (v1)". Reject any agent output that adds:

- Two-way sync, reverse sync stubs, or "future-proofing" hooks for two-way.
- Multiple calendar pairs (config schema is locked single-pair).
- Categories / colors / reminders / attachments mapping.
- Free/busy-only mode toggle.
- Webhook/push-notification scaffolding from Graph.
- Any GUI surface (including a `--gui` CLI flag).
- Multi-user packaging (no per-user templating in install.sh beyond the current user).
- Auto-update mechanism.
- Schema migration framework (single `schema_version` row is fine; a migrator is not).
- `copy_attendees=true` code path (locked false; config validation rejects it).
