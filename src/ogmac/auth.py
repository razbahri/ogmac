from __future__ import annotations

import json
import logging

import keyring
import msal
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from ogmac.config import Config

log = logging.getLogger(__name__)

GRAPH_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
_GRAPH_AUTHORITY = "https://login.microsoftonline.com/common"
_GRAPH_SCOPES = ["Calendars.Read"]
_GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
_MS_KEYCHAIN_SERVICE = "ogmac.microsoft"
_GOOGLE_KEYCHAIN_SERVICE = "ogmac.google"


class AuthError(Exception):
    pass


class TokenRefreshError(AuthError):
    pass


def _load_cache(service: str, account: str) -> str | None:
    return keyring.get_password(service, account)


def _save_cache(service: str, account: str, blob: str) -> None:
    keyring.set_password(service, account, blob)


def _build_msal_app(config: Config) -> tuple[msal.PublicClientApplication, msal.SerializableTokenCache]:
    cache = msal.SerializableTokenCache()
    blob = _load_cache(_MS_KEYCHAIN_SERVICE, config.outlook.account)
    if blob:
        cache.deserialize(blob)
    app = msal.PublicClientApplication(
        GRAPH_CLIENT_ID,
        authority=_GRAPH_AUTHORITY,
        token_cache=cache,
    )
    return app, cache


def _flush_msal_cache(cache: msal.SerializableTokenCache, account: str) -> None:
    if cache.has_state_changed:
        _save_cache(_MS_KEYCHAIN_SERVICE, account, cache.serialize())


def get_graph_token(config: Config) -> str:
    app, cache = _build_msal_app(config)
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(_GRAPH_SCOPES, account=accounts[0])
    _flush_msal_cache(cache, config.outlook.account)
    if not result or "access_token" not in result:
        raise TokenRefreshError(
            "Silent token acquisition failed; run 'ogmac login' to re-authenticate."
        )
    return result["access_token"]


def get_google_credentials(config: Config) -> Credentials:
    blob = _load_cache(_GOOGLE_KEYCHAIN_SERVICE, config.google.account)
    if not blob:
        raise TokenRefreshError(
            "No Google credentials in Keychain; run 'ogmac login' to authenticate."
        )
    creds = Credentials.from_authorized_user_info(json.loads(blob), _GOOGLE_SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                raise TokenRefreshError(f"Google token refresh failed: {exc}") from exc
        else:
            raise TokenRefreshError(
                "Google credentials invalid and cannot be refreshed; run 'ogmac login'."
            )
    _save_cache(_GOOGLE_KEYCHAIN_SERVICE, config.google.account, creds.to_json())
    return creds


def login_microsoft(config: Config) -> None:
    app, cache = _build_msal_app(config)
    result = app.acquire_token_interactive(scopes=_GRAPH_SCOPES)
    if not result or "access_token" not in result:
        raise AuthError(f"Microsoft interactive login failed: {result.get('error_description', result)}")
    _flush_msal_cache(cache, config.outlook.account)


def login_google(config: Config) -> None:
    flow = InstalledAppFlow.from_client_secrets_file(
        str(config.google.client_secret_path),
        scopes=_GOOGLE_SCOPES,
    )
    creds = flow.run_local_server(port=0)
    _save_cache(_GOOGLE_KEYCHAIN_SERVICE, config.google.account, creds.to_json())
