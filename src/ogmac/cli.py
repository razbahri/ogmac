from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

from ogmac.auth import TokenRefreshError, get_google_credentials, get_graph_token, login_google, login_microsoft
from ogmac.config import Config, ConfigError
from ogmac.google import apply_action, fetch_target_events, find_orphan_by_instance_id
from ogmac.logging_setup import setup_logging
from ogmac.models import ActionKind
from ogmac.notify import notify
from ogmac.outlook import fetch_source_events as fetch_via_microsoft_graph
from ogmac.outlook_eventkit import fetch_source_events as fetch_via_apple_calendar
from ogmac.reconciler import reconcile
from ogmac.state import State

log = logging.getLogger(__name__)


def state_db_path() -> Path:
    p = Path.home() / "Library" / "Application Support" / "ogmac" / "state.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compute_sync_window(
    now: datetime,
    past_days: int,
    future_days: int,
    tz: tzinfo | None = None,
) -> tuple[datetime, datetime]:
    """Day-aligned `[start, end)` window in `tz` (default: system local).

    `start` is midnight `past_days` days before today; `end` is midnight
    `future_days + 1` days after today (exclusive). Returned datetimes are
    UTC-aware so the rest of the pipeline can use them directly.

    Day-aligned avoids boundary churn within a day: every sync of the
    same calendar day evaluates the same window.
    """
    local = now.astimezone(tz)
    local_midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_local = local_midnight - timedelta(days=past_days)
    end_local = local_midnight + timedelta(days=future_days + 1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _finalize_success(state: State, duration_ms: int) -> None:
    state.reset_failures()
    state.set_run_state("last_success_at", _utcnow_iso())
    log.info("sync.success duration_ms=%d", duration_ms)


def _finalize_failure(state: State, cfg: Config, error: Exception) -> None:
    n = state.increment_failures()
    log.error("sync.failure n=%d type=%s", n, type(error).__name__)
    if n >= cfg.failure.max_consecutive_before_disable:
        state.disable(f"{n} consecutive failures: {error}")
        if cfg.failure.notify_on_failure:
            notify(
                title="ogmac auto-disabled",
                body=f"{n} consecutive failures. Run 'ogmac status' and 'ogmac resume'.",
                sticky=True,
            )
    elif n == 1 and cfg.failure.notify_on_failure:
        notify(title="ogmac sync failed", body=f"{type(error).__name__}: {error}")


def _run_sync(cfg: Config, state: State) -> int:
    if state.is_disabled:
        log.info("sync.skipped reason=disabled")
        return 0
    if state.is_paused:
        log.info("sync.skipped reason=paused")
        return 0

    t_start = time.monotonic()
    start, end = _compute_sync_window(
        _utcnow(),
        cfg.sync.window_past_days,
        cfg.sync.window_future_days,
    )

    log.info(
        "sync.start window=[%s..%s)",
        start.astimezone().strftime("%Y-%m-%d"),
        end.astimezone().strftime("%Y-%m-%d"),
    )

    try:
        google_creds = get_google_credentials(cfg)
        if cfg.outlook.read_method == "microsoft_graph":
            outlook_token = get_graph_token(cfg)
        else:
            outlook_token = ""
    except TokenRefreshError as exc:
        _finalize_failure(state, cfg, exc)
        return 1

    if cfg.outlook.read_method == "microsoft_graph":
        sources = fetch_via_microsoft_graph(outlook_token, cfg.outlook.source_calendar, start, end)
    else:
        sources = fetch_via_apple_calendar(outlook_token, cfg.outlook.source_calendar, start, end)
    log.info("outlook.fetch count=%d method=%s", len(sources), cfg.outlook.read_method)

    targets = fetch_target_events(google_creds, cfg.google.target_calendar_id, start, end)
    log.info("google.fetch count=%d", len(targets))

    existing_instance_ids = {t.instance_id for t in targets}
    mapped_instance_ids = {m.instance_id for m in state.all_mappings()}
    for src in sources:
        if src.instance_id not in existing_instance_ids and src.instance_id not in mapped_instance_ids:
            orphan = find_orphan_by_instance_id(google_creds, cfg.google.target_calendar_id, src.instance_id)
            if orphan is not None:
                log.info("sync.orphan_adopted instance_id=%s", src.instance_id)
                targets.append(orphan)
                existing_instance_ids.add(src.instance_id)

    actions = reconcile(sources, targets)

    creates = sum(1 for a in actions if a.kind is ActionKind.CREATE)
    updates = sum(1 for a in actions if a.kind is ActionKind.UPDATE)
    deletes = sum(1 for a in actions if a.kind is ActionKind.DELETE)
    skips = sum(1 for a in actions if a.kind is ActionKind.SKIP)
    log.info("reconcile create=%d update=%d delete=%d skip=%d", creates, updates, deletes, skips)

    any_failure: Exception | None = None
    for action in actions:
        if action.kind is ActionKind.SKIP:
            continue
        try:
            returned_id = apply_action(google_creds, cfg.google.target_calendar_id, action)
            if action.kind is ActionKind.CREATE:
                state.put_mapping(action.source.instance_id, returned_id, action.source.last_modified)
                log.info("google.create instance_id=%s google_id=%s", action.source.instance_id, returned_id)
            elif action.kind is ActionKind.UPDATE:
                state.put_mapping(action.source.instance_id, action.target.google_id, action.source.last_modified)
                log.info("google.update instance_id=%s google_id=%s", action.source.instance_id, action.target.google_id)
            elif action.kind is ActionKind.DELETE:
                state.delete_mapping(action.target.instance_id)
                log.info("google.delete instance_id=%s google_id=%s", action.target.instance_id, action.target.google_id)
        except Exception as exc:
            log.error("action.failed kind=%s error=%s", action.kind.value, type(exc).__name__)
            if any_failure is None:
                any_failure = exc

    duration_ms = int((time.monotonic() - t_start) * 1000)
    if any_failure is None:
        _finalize_success(state, duration_ms)
        return 0
    else:
        _finalize_failure(state, cfg, any_failure)
        return 1


def _cmd_sync(args: argparse.Namespace, cfg: Config) -> int:
    state = State(state_db_path())
    try:
        return _run_sync(cfg, state)
    finally:
        state.close()


def _cmd_login(args: argparse.Namespace, cfg: Config) -> int:
    provider = getattr(args, "provider", None)
    needs_microsoft = cfg.outlook.read_method == "microsoft_graph"

    if provider == "microsoft":
        if not needs_microsoft:
            print(
                "outlook.read_method is 'apple_calendar'; Microsoft login is not used. "
                "Configure Exchange in System Settings → Internet Accounts instead, "
                "or set outlook.read_method: microsoft_graph in config.yaml."
            )
            return 1
        login_microsoft(cfg)
        print("Microsoft login complete.")
    elif provider == "google":
        login_google(cfg)
        print("Google login complete.")
    else:
        if needs_microsoft:
            login_microsoft(cfg)
            print("Microsoft login complete.")
        login_google(cfg)
        print("Google login complete.")
    return 0


def _cmd_status(args: argparse.Namespace, cfg: Config) -> int:
    state = State(state_db_path())
    try:
        last_success = state.get_run_state("last_success_at") or "never"
        failures = state.consecutive_failures
        disabled = state.is_disabled
        disable_reason = state.get_run_state("disable_reason") or ""

        print("ogmac status")
        print(f"  last_success_at: {last_success}")
        print(f"  consecutive_failures: {failures}")
        if disabled:
            print(f"  disabled: true — reason: {disable_reason}")
        else:
            print("  disabled: false")

        if disabled:
            return 1
        if last_success == "never":
            return 1
        try:
            last_dt = datetime.fromisoformat(last_success.replace("Z", "+00:00"))
            if (_utcnow() - last_dt) > timedelta(hours=24):
                return 1
        except ValueError:
            return 1
        return 0
    finally:
        state.close()


def _cmd_pause(args: argparse.Namespace, cfg: Config) -> int:
    state = State(state_db_path())
    try:
        state.pause()
        log.info("pause: set paused flag")
        return 0
    finally:
        state.close()


def _cmd_unpause(args: argparse.Namespace, cfg: Config) -> int:
    state = State(state_db_path())
    try:
        state.unpause()
        log.info("unpause: cleared paused flag")
        return 0
    finally:
        state.close()


def _cmd_resume(args: argparse.Namespace, cfg: Config) -> int:
    state = State(state_db_path())
    try:
        state.enable()
        state.reset_failures()
        log.info("resume: cleared disabled flag, running sync")
        return _run_sync(cfg, state)
    finally:
        state.close()


def _cmd_reset(args: argparse.Namespace, cfg: Config) -> int:
    skip_confirm = getattr(args, "yes", False)
    if not skip_confirm:
        print(
            "This will delete all ogmac-owned events from the target Google calendar "
            "and wipe local state. Continue? [yes/N]: ",
            end="",
            flush=True,
        )
        answer = sys.stdin.readline().strip()
        if answer != "yes":
            print("Aborted.")
            return 1

    state = State(state_db_path())
    try:
        try:
            google_creds = get_google_credentials(cfg)
        except TokenRefreshError as exc:
            print(f"Token error: {exc}. Run 'ogmac login' first.")
            return 1

        from datetime import timedelta as _td
        start = _utcnow() - _td(days=365)
        end = _utcnow() + _td(days=365)
        targets = fetch_target_events(google_creds, cfg.google.target_calendar_id, start, end)

        state.wipe_event_map()

        from ogmac.models import Action as _Action, ActionKind as _ActionKind
        for tgt in targets:
            delete_action = _Action(kind=_ActionKind.DELETE, source=None, target=tgt)
            try:
                apply_action(google_creds, cfg.google.target_calendar_id, delete_action)
            except Exception as exc:
                log.error("reset.delete_failed google_id=%s error=%s", tgt.google_id, type(exc).__name__)

        state.wipe_run_state()
        print("Reset complete.")
        print("Tokens preserved. Run 'ogmac login' to re-authenticate.")
        return 0
    finally:
        state.close()


def main(argv: list[str] | None = None) -> int:
    setup_logging(debug=os.environ.get("OGMAC_DEBUG") == "1")

    parser = argparse.ArgumentParser(
        prog="ogmac",
        description="One-way Outlook → Google Calendar sync for macOS.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("sync", help="Run a sync cycle (launchd path).")

    login_parser = subparsers.add_parser("login", help="Authenticate with Microsoft and/or Google.")
    login_parser.add_argument("provider", nargs="?", choices=["microsoft", "google"], help="Provider to authenticate.")

    subparsers.add_parser("status", help="Print sync state and exit with code reflecting health.")

    subparsers.add_parser("pause", help="Pause syncing until 'ogmac unpause'.")
    subparsers.add_parser("unpause", help="Resume syncing after 'ogmac pause'.")

    subparsers.add_parser("resume", help="Clear disabled flag and run sync immediately.")

    reset_parser = subparsers.add_parser("reset", help="Wipe all ogmac-owned Google events and local state.")
    reset_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "status":
        cfg_path = Config.default_path()
        if not cfg_path.exists():
            print(f"Config not found at {cfg_path}. Copy from docs/example-config.yaml.")
            return 2
        try:
            cfg = Config.load(cfg_path)
        except ConfigError as exc:
            log.error("config.error %s", exc)
            return 2
        return _cmd_status(args, cfg)

    cfg_path = Config.default_path()
    if not cfg_path.exists():
        print(
            f"Config not found at {cfg_path}.\n"
            "Create ~/.config/ogmac/config.yaml — see README for a complete example."
        )
        return 2
    try:
        cfg = Config.load(cfg_path)
    except ConfigError as exc:
        log.error("config.error %s", exc)
        return 2

    if args.command == "sync":
        return _cmd_sync(args, cfg)
    elif args.command == "login":
        return _cmd_login(args, cfg)
    elif args.command == "pause":
        return _cmd_pause(args, cfg)
    elif args.command == "unpause":
        return _cmd_unpause(args, cfg)
    elif args.command == "resume":
        return _cmd_resume(args, cfg)
    elif args.command == "reset":
        return _cmd_reset(args, cfg)

    parser.print_help()
    return 0
