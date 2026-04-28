from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


from ogmac.notify import notify


class TestNotifyBanner:
    def test_uses_display_notification(self):
        with patch("ogmac.notify.subprocess.run") as mock_run:
            notify("Title", "Body text")

        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"
        assert "display notification" in args[2]
        assert "display alert" not in args[2]

    def test_banner_contains_quoted_title_and_body(self):
        with patch("ogmac.notify.subprocess.run") as mock_run:
            notify("My Title", "My Body")

        script = mock_run.call_args[0][0][2]
        assert json.dumps("My Body") in script
        assert json.dumps("My Title") in script

    def test_banner_special_chars_quoted(self):
        with patch("ogmac.notify.subprocess.run") as mock_run:
            notify('Say "hello"', "It's fine\nnewline")

        script = mock_run.call_args[0][0][2]
        assert json.dumps('Say "hello"') in script
        assert json.dumps("It's fine\nnewline") in script

    def test_banner_failure_logged_not_raised(self):
        with (
            patch("ogmac.notify.subprocess.run", side_effect=OSError("no osascript")),
            patch("ogmac.notify.log") as mock_log,
        ):
            notify("T", "B")

        mock_log.warning.assert_called_once()

    def test_banner_does_not_raise_on_failure(self):
        with patch("ogmac.notify.subprocess.run", side_effect=OSError("broken")):
            notify("T", "B")


class TestNotifySticky:
    def test_sticky_uses_display_alert(self):
        with patch("ogmac.notify.subprocess.Popen") as mock_popen:
            notify("Alert Title", "Alert Body", sticky=True)

        script = mock_popen.call_args[0][0][2]
        assert "display alert" in script
        assert "display notification" not in script

    def test_sticky_contains_title_and_body(self):
        with patch("ogmac.notify.subprocess.Popen") as mock_popen:
            notify("My Alert", "Something bad", sticky=True)

        script = mock_popen.call_args[0][0][2]
        assert json.dumps("My Alert") in script
        assert json.dumps("Something bad") in script

    def test_sticky_launched_detached(self):
        with patch("ogmac.notify.subprocess.Popen") as mock_popen:
            notify("T", "B", sticky=True)

        kwargs = mock_popen.call_args[1]
        assert kwargs.get("start_new_session") is True

    def test_sticky_does_not_wait(self):
        mock_proc = MagicMock()
        with patch("ogmac.notify.subprocess.Popen", return_value=mock_proc):
            notify("T", "B", sticky=True)

        mock_proc.wait.assert_not_called()
        mock_proc.communicate.assert_not_called()

    def test_sticky_uses_popen_not_run(self):
        with (
            patch("ogmac.notify.subprocess.Popen") as mock_popen,
            patch("ogmac.notify.subprocess.run") as mock_run,
        ):
            notify("T", "B", sticky=True)

        mock_popen.assert_called_once()
        mock_run.assert_not_called()

    def test_sticky_failure_logged_not_raised(self):
        with (
            patch("ogmac.notify.subprocess.Popen", side_effect=OSError("no osascript")),
            patch("ogmac.notify.log") as mock_log,
        ):
            notify("T", "B", sticky=True)

        mock_log.warning.assert_called_once()

    def test_sticky_does_not_raise_on_failure(self):
        with patch("ogmac.notify.subprocess.Popen", side_effect=OSError("broken")):
            notify("T", "B", sticky=True)
