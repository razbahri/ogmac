from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ogmac.auth import (
    GRAPH_CLIENT_ID,
    TokenRefreshError,
    _load_cache,
    _save_cache,
    get_google_credentials,
    get_graph_token,
    login_google,
    login_microsoft,
)
from ogmac.config import Config


@pytest.fixture()
def config(tmp_path: Path) -> Config:
    secret = tmp_path / "client_secret.json"
    secret.write_text("{}")
    return Config.model_validate(
        {
            "outlook": {"account": "user@example.com"},
            "google": {
                "account": "user@gmail.com",
                "client_secret_path": str(secret),
                "target_calendar_id": "cal123",
            },
        }
    )


class TestKeychainHelpers:
    def test_load_cache_calls_get_password(self):
        with patch("ogmac.auth.keyring.get_password", return_value="blob") as mock_get:
            result = _load_cache("svc", "acct")
        mock_get.assert_called_once_with("svc", "acct")
        assert result == "blob"

    def test_load_cache_returns_none_when_missing(self):
        with patch("ogmac.auth.keyring.get_password", return_value=None):
            assert _load_cache("svc", "acct") is None

    def test_save_cache_calls_set_password(self):
        with patch("ogmac.auth.keyring.set_password") as mock_set:
            _save_cache("svc", "acct", "blob")
        mock_set.assert_called_once_with("svc", "acct", "blob")


class TestGetGraphToken:
    def _make_cache(self, blob: str | None = None, changed: bool = False):
        cache = MagicMock()
        cache.has_state_changed = changed
        cache.serialize.return_value = "serialized"
        return cache

    def test_returns_access_token_on_success(self, config: Config):
        mock_cache = self._make_cache(changed=False)
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_app.acquire_token_silent.return_value = {"access_token": "tok123"}

        with (
            patch("ogmac.auth.msal.SerializableTokenCache", return_value=mock_cache),
            patch("ogmac.auth.msal.PublicClientApplication", return_value=mock_app),
            patch("ogmac.auth.keyring.get_password", return_value=None),
            patch("ogmac.auth.keyring.set_password"),
        ):
            token = get_graph_token(config)

        assert token == "tok123"

    def test_raises_token_refresh_error_when_silent_returns_none(self, config: Config):
        mock_cache = self._make_cache()
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{"username": "user@example.com"}]
        mock_app.acquire_token_silent.return_value = None

        with (
            patch("ogmac.auth.msal.SerializableTokenCache", return_value=mock_cache),
            patch("ogmac.auth.msal.PublicClientApplication", return_value=mock_app),
            patch("ogmac.auth.keyring.get_password", return_value=None),
            patch("ogmac.auth.keyring.set_password"),
        ):
            with pytest.raises(TokenRefreshError):
                get_graph_token(config)

    def test_raises_token_refresh_error_when_no_accounts(self, config: Config):
        mock_cache = self._make_cache()
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = []

        with (
            patch("ogmac.auth.msal.SerializableTokenCache", return_value=mock_cache),
            patch("ogmac.auth.msal.PublicClientApplication", return_value=mock_app),
            patch("ogmac.auth.keyring.get_password", return_value=None),
            patch("ogmac.auth.keyring.set_password"),
        ):
            with pytest.raises(TokenRefreshError):
                get_graph_token(config)

    def test_cache_loaded_from_keyring(self, config: Config):
        mock_cache = self._make_cache()
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{}]
        mock_app.acquire_token_silent.return_value = {"access_token": "t"}

        with (
            patch("ogmac.auth.msal.SerializableTokenCache", return_value=mock_cache),
            patch("ogmac.auth.msal.PublicClientApplication", return_value=mock_app),
            patch("ogmac.auth.keyring.get_password", return_value="existing_blob") as mock_get,
            patch("ogmac.auth.keyring.set_password"),
        ):
            get_graph_token(config)

        mock_get.assert_called_with("ogmac.microsoft", config.outlook.account)
        mock_cache.deserialize.assert_called_once_with("existing_blob")

    def test_cache_persisted_when_changed(self, config: Config):
        mock_cache = self._make_cache(changed=True)
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{}]
        mock_app.acquire_token_silent.return_value = {"access_token": "t"}

        with (
            patch("ogmac.auth.msal.SerializableTokenCache", return_value=mock_cache),
            patch("ogmac.auth.msal.PublicClientApplication", return_value=mock_app),
            patch("ogmac.auth.keyring.get_password", return_value=None),
            patch("ogmac.auth.keyring.set_password") as mock_set,
        ):
            get_graph_token(config)

        mock_set.assert_called_once_with("ogmac.microsoft", config.outlook.account, "serialized")

    def test_cache_not_persisted_when_unchanged(self, config: Config):
        mock_cache = self._make_cache(changed=False)
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{}]
        mock_app.acquire_token_silent.return_value = {"access_token": "t"}

        with (
            patch("ogmac.auth.msal.SerializableTokenCache", return_value=mock_cache),
            patch("ogmac.auth.msal.PublicClientApplication", return_value=mock_app),
            patch("ogmac.auth.keyring.get_password", return_value=None),
            patch("ogmac.auth.keyring.set_password") as mock_set,
        ):
            get_graph_token(config)

        mock_set.assert_not_called()

    def test_correct_scopes_and_client_id(self, config: Config):
        mock_cache = self._make_cache()
        mock_app = MagicMock()
        mock_app.get_accounts.return_value = [{}]
        mock_app.acquire_token_silent.return_value = {"access_token": "t"}

        with (
            patch("ogmac.auth.msal.SerializableTokenCache", return_value=mock_cache),
            patch("ogmac.auth.msal.PublicClientApplication", return_value=mock_app) as mock_cls,
            patch("ogmac.auth.keyring.get_password", return_value=None),
            patch("ogmac.auth.keyring.set_password"),
        ):
            get_graph_token(config)

        mock_cls.assert_called_once_with(
            GRAPH_CLIENT_ID,
            authority="https://login.microsoftonline.com/common",
            token_cache=mock_cache,
        )
        mock_app.acquire_token_silent.assert_called_once_with(
            ["Calendars.Read"], account=mock_app.get_accounts.return_value[0]
        )


class TestGetGoogleCredentials:
    def _make_creds_blob(self, valid: bool = True, expired: bool = False, has_refresh: bool = True) -> str:
        return json.dumps({
            "token": "tok",
            "refresh_token": "ref" if has_refresh else None,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "cid",
            "client_secret": "csec",
            "scopes": ["https://www.googleapis.com/auth/calendar.events"],
        })

    def test_returns_valid_credentials(self, config: Config):
        blob = self._make_creds_blob()
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.to_json.return_value = blob

        with (
            patch("ogmac.auth.keyring.get_password", return_value=blob),
            patch("ogmac.auth.keyring.set_password"),
            patch("ogmac.auth.Credentials.from_authorized_user_info", return_value=mock_creds),
        ):
            creds = get_google_credentials(config)

        assert creds is mock_creds

    def test_raises_when_no_keychain_entry(self, config: Config):
        with patch("ogmac.auth.keyring.get_password", return_value=None):
            with pytest.raises(TokenRefreshError):
                get_google_credentials(config)

    def test_refreshes_expired_credentials(self, config: Config):
        blob = self._make_creds_blob()
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "ref"
        mock_creds.to_json.return_value = blob

        with (
            patch("ogmac.auth.keyring.get_password", return_value=blob),
            patch("ogmac.auth.keyring.set_password"),
            patch("ogmac.auth.Credentials.from_authorized_user_info", return_value=mock_creds),
            patch("ogmac.auth.Request"),
        ):
            creds = get_google_credentials(config)

        mock_creds.refresh.assert_called_once()
        assert creds is mock_creds

    def test_raises_when_refresh_fails(self, config: Config):
        blob = self._make_creds_blob()
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "ref"
        mock_creds.refresh.side_effect = Exception("network error")

        with (
            patch("ogmac.auth.keyring.get_password", return_value=blob),
            patch("ogmac.auth.keyring.set_password"),
            patch("ogmac.auth.Credentials.from_authorized_user_info", return_value=mock_creds),
            patch("ogmac.auth.Request"),
        ):
            with pytest.raises(TokenRefreshError):
                get_google_credentials(config)

    def test_raises_when_invalid_no_refresh_token(self, config: Config):
        blob = self._make_creds_blob()
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = False
        mock_creds.refresh_token = None

        with (
            patch("ogmac.auth.keyring.get_password", return_value=blob),
            patch("ogmac.auth.keyring.set_password"),
            patch("ogmac.auth.Credentials.from_authorized_user_info", return_value=mock_creds),
        ):
            with pytest.raises(TokenRefreshError):
                get_google_credentials(config)

    def test_persists_refreshed_credentials(self, config: Config):
        blob = self._make_creds_blob()
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "ref"
        mock_creds.to_json.return_value = '{"refreshed": true}'

        with (
            patch("ogmac.auth.keyring.get_password", return_value=blob),
            patch("ogmac.auth.keyring.set_password") as mock_set,
            patch("ogmac.auth.Credentials.from_authorized_user_info", return_value=mock_creds),
            patch("ogmac.auth.Request"),
        ):
            get_google_credentials(config)

        mock_set.assert_called_once_with(
            "ogmac.google", config.google.account, '{"refreshed": true}'
        )

    def test_correct_scopes_passed(self, config: Config):
        blob = self._make_creds_blob()
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.to_json.return_value = blob

        with (
            patch("ogmac.auth.keyring.get_password", return_value=blob),
            patch("ogmac.auth.keyring.set_password"),
            patch("ogmac.auth.Credentials.from_authorized_user_info", return_value=mock_creds) as mock_from,
        ):
            get_google_credentials(config)

        mock_from.assert_called_once_with(
            json.loads(blob), ["https://www.googleapis.com/auth/calendar.events"]
        )


class TestLoginMicrosoft:
    def test_calls_acquire_token_interactive(self, config: Config):
        mock_cache = MagicMock()
        mock_cache.has_state_changed = True
        mock_cache.serialize.return_value = "blob"
        mock_app = MagicMock()
        mock_app.acquire_token_interactive.return_value = {"access_token": "t"}

        with (
            patch("ogmac.auth.msal.SerializableTokenCache", return_value=mock_cache),
            patch("ogmac.auth.msal.PublicClientApplication", return_value=mock_app),
            patch("ogmac.auth.keyring.get_password", return_value=None),
            patch("ogmac.auth.keyring.set_password") as mock_set,
        ):
            login_microsoft(config)

        mock_app.acquire_token_interactive.assert_called_once_with(scopes=["Calendars.Read"])
        mock_set.assert_called_once_with("ogmac.microsoft", config.outlook.account, "blob")


class TestLoginGoogle:
    def test_calls_run_local_server_and_persists(self, config: Config):
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "t"}'
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds

        with (
            patch("ogmac.auth.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow) as mock_from,
            patch("ogmac.auth.keyring.set_password") as mock_set,
        ):
            login_google(config)

        mock_from.assert_called_once_with(
            str(config.google.client_secret_path),
            scopes=["https://www.googleapis.com/auth/calendar.events"],
        )
        mock_flow.run_local_server.assert_called_once_with(port=0)
        mock_set.assert_called_once_with("ogmac.google", config.google.account, '{"token": "t"}')
