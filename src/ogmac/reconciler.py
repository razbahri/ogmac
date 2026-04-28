from __future__ import annotations

from ogmac.models import Action, ActionKind, SourceEvent, TargetEvent


def reconcile(sources: list[SourceEvent], targets: list[TargetEvent]) -> list[Action]:
    S: dict[str, SourceEvent] = {ev.instance_id: ev for ev in sources if not ev.is_cancelled}
    T: dict[str, TargetEvent] = {ev.instance_id: ev for ev in targets}

    actions: list[Action] = []

    for instance_id in S.keys() | T.keys():
        src = S.get(instance_id)
        tgt = T.get(instance_id)

        if src is not None and tgt is None:
            actions.append(Action(kind=ActionKind.CREATE, source=src, target=None))
        elif src is not None and tgt is not None:
            if src.last_modified > tgt.last_synced_outlook_modified:
                actions.append(Action(kind=ActionKind.UPDATE, source=src, target=tgt))
            else:
                actions.append(Action(kind=ActionKind.SKIP, source=src, target=tgt))
        elif src is None and tgt is not None:
            actions.append(Action(kind=ActionKind.DELETE, source=None, target=tgt))

    return actions
