from __future__ import annotations

import json
import logging
import subprocess

log = logging.getLogger(__name__)


def notify(title: str, body: str, sticky: bool = False) -> None:
    if sticky:
        script = f"display alert {json.dumps(title)} message {json.dumps(body)}"
        try:
            subprocess.Popen(
                ["osascript", "-e", script],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            log.warning("notify: failed to launch sticky alert: %s", exc)
    else:
        script = f"display notification {json.dumps(body)} with title {json.dumps(title)}"
        try:
            subprocess.run(
                ["osascript", "-e", script],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            log.warning("notify: failed to display notification: %s", exc)
