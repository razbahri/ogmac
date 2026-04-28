from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ogmac.models import ActionKind, SourceEvent, TargetEvent
from ogmac.reconciler import reconcile

T0 = datetime(2026, 4, 28, 10, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 4, 28, 11, 0, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)
TMIN = datetime.min.replace(tzinfo=timezone.utc)


def make_source(
    instance_id: str = "iid-1",
    last_modified: datetime = T1,
    is_cancelled: bool = False,
) -> SourceEvent:
    return SourceEvent(
        outlook_id="oid-1",
        instance_id=instance_id,
        subject="Meeting",
        start_utc=T0,
        end_utc=T1,
        location=None,
        body_text="",
        last_modified=last_modified,
        is_cancelled=is_cancelled,
    )


def make_target(
    instance_id: str = "iid-1",
    last_synced_outlook_modified: datetime = T1,
) -> TargetEvent:
    return TargetEvent(
        google_id="gid-1",
        etag="etag-1",
        instance_id=instance_id,
        last_synced_outlook_modified=last_synced_outlook_modified,
    )


# ── parametrized matrix cases ─────────────────────────────────────────────────

@pytest.mark.parametrize(
    "sources, targets, expected_kinds",
    [
        pytest.param(
            [make_source()],
            [],
            [ActionKind.CREATE],
            id="source-only-creates",
        ),
        pytest.param(
            [],
            [make_target()],
            [ActionKind.DELETE],
            id="target-only-deletes",
        ),
        pytest.param(
            [make_source(last_modified=T1)],
            [make_target(last_synced_outlook_modified=T1)],
            [ActionKind.SKIP],
            id="both-no-change-skips",
        ),
        pytest.param(
            [make_source(last_modified=T2)],
            [make_target(last_synced_outlook_modified=T1)],
            [ActionKind.UPDATE],
            id="both-source-modified-updates",
        ),
        pytest.param(
            [make_source(is_cancelled=True)],
            [make_target()],
            [ActionKind.DELETE],
            id="cancelled-occurrence-deletes",
        ),
        pytest.param(
            [],
            [make_target()],
            [ActionKind.DELETE],
            id="source-out-of-window-deletes",
        ),
        pytest.param(
            [make_source(last_modified=T1)],
            [make_target(last_synced_outlook_modified=TMIN)],
            [ActionKind.UPDATE],
            id="duplicate-adoption-is-update",
        ),
    ],
)
def test_reconcile_matrix(
    sources: list[SourceEvent],
    targets: list[TargetEvent],
    expected_kinds: list[ActionKind],
) -> None:
    actions = reconcile(sources, targets)
    assert [a.kind for a in actions] == expected_kinds


# ── per-case payload assertions ───────────────────────────────────────────────

def test_create_carries_source() -> None:
    src = make_source()
    (action,) = reconcile([src], [])
    assert action.source is src
    assert action.target is None


def test_delete_carries_target() -> None:
    tgt = make_target()
    (action,) = reconcile([], [tgt])
    assert action.target is tgt
    assert action.source is None


def test_update_carries_both() -> None:
    src = make_source(last_modified=T2)
    tgt = make_target(last_synced_outlook_modified=T1)
    (action,) = reconcile([src], [tgt])
    assert action.source is src
    assert action.target is tgt


def test_skip_carries_both() -> None:
    src = make_source(last_modified=T1)
    tgt = make_target(last_synced_outlook_modified=T1)
    (action,) = reconcile([src], [tgt])
    assert action.source is src
    assert action.target is tgt


# ── target-without-marker contract ───────────────────────────────────────────
# The reconciler contract requires the caller to filter out events that lack
# the ogmac_owned marker before calling reconcile().  This test documents that
# contract: only marker-bearing TargetEvents reach reconcile(), so the function
# never needs to inspect or reject unmarked events.

def test_reconciler_only_receives_marker_bearing_targets() -> None:
    tgt = make_target()
    actions = reconcile([], [tgt])
    assert len(actions) == 1
    assert actions[0].kind == ActionKind.DELETE


# ── edge cases ────────────────────────────────────────────────────────────────

def test_empty_inputs_return_no_actions() -> None:
    assert reconcile([], []) == []


def test_multiple_events_mixed_actions() -> None:
    src_create = make_source(instance_id="new")
    src_skip = make_source(instance_id="same", last_modified=T1)
    src_update = make_source(instance_id="changed", last_modified=T2)
    src_cancelled = make_source(instance_id="gone", is_cancelled=True)

    tgt_skip = make_target(instance_id="same", last_synced_outlook_modified=T1)
    tgt_update = make_target(instance_id="changed", last_synced_outlook_modified=T1)
    tgt_delete = make_target(instance_id="orphan")
    tgt_cancelled = make_target(instance_id="gone")

    actions = reconcile(
        [src_create, src_skip, src_update, src_cancelled],
        [tgt_skip, tgt_update, tgt_delete, tgt_cancelled],
    )

    kinds_by_id = {a.source.instance_id if a.source else a.target.instance_id: a.kind for a in actions}
    assert kinds_by_id["new"] == ActionKind.CREATE
    assert kinds_by_id["same"] == ActionKind.SKIP
    assert kinds_by_id["changed"] == ActionKind.UPDATE
    assert kinds_by_id["orphan"] == ActionKind.DELETE
    assert kinds_by_id["gone"] == ActionKind.DELETE


def test_cancelled_without_target_emits_nothing() -> None:
    src = make_source(is_cancelled=True)
    assert reconcile([src], []) == []


def test_equal_modified_timestamp_is_skip_not_update() -> None:
    src = make_source(last_modified=T1)
    tgt = make_target(last_synced_outlook_modified=T1)
    (action,) = reconcile([src], [tgt])
    assert action.kind == ActionKind.SKIP
