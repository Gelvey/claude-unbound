"""Renewable Google Application Default Credentials for Vertex AI."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable

import httpx
import requests
from google.auth import default as google_auth_default
from google.auth.credentials import Credentials
from google.auth.exceptions import (
    DefaultCredentialsError,
    GoogleAuthError,
    RefreshError,
    TransportError,
)
from google.auth.transport.requests import Request

from providers.exceptions import AuthenticationError, ServiceUnavailableError

GOOGLE_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

CredentialsLoader = Callable[[], tuple[Credentials, str | None]]


def load_application_default_credentials() -> tuple[Credentials, str | None]:
    """Load ADC with the scope required by Vertex AI."""
    return google_auth_default(scopes=(GOOGLE_CLOUD_PLATFORM_SCOPE,))


class GoogleAccessTokenProvider:
    """Return a valid ADC access token, refreshing without blocking the event loop."""

    def __init__(
        self,
        credentials_loader: CredentialsLoader = load_application_default_credentials,
        *,
        proxy: str = "",
    ) -> None:
        self._credentials_loader = credentials_loader
        self._proxy = proxy
        self._credentials: Credentials | None = None
        self._refresh_lock = asyncio.Lock()

    async def get_token(self) -> str:
        credentials = self._credentials
        if credentials is not None and credentials.valid and credentials.token:
            return credentials.token

        async with self._refresh_lock:
            credentials = self._credentials
            if credentials is not None and credentials.valid and credentials.token:
                return credentials.token
            try:
                if credentials is None:
                    loaded, _project = await asyncio.to_thread(self._credentials_loader)
                    credentials = loaded
                    self._credentials = loaded
                if not credentials.valid or not credentials.token:
                    await asyncio.to_thread(self._refresh, credentials)
                token = credentials.token
                if not isinstance(token, str) or not token:
                    raise RefreshError("Google credentials returned no access token.")
                return token
            except (DefaultCredentialsError, RefreshError, TransportError) as exc:
                raise _google_auth_failure(exc) from exc
            except GoogleAuthError as exc:
                raise _google_auth_failure(exc) from exc

    def _refresh(self, credentials: Credentials) -> None:
        with requests.Session() as session:
            if self._proxy:
                session.proxies.update({"http": self._proxy, "https": self._proxy})
            credentials.refresh(Request(session=session))


def _google_auth_failure(
    exc: DefaultCredentialsError | RefreshError | TransportError | GoogleAuthError,
) -> AuthenticationError | ServiceUnavailableError:
    if isinstance(exc, TransportError) or (
        isinstance(exc, RefreshError) and bool(getattr(exc, "retryable", False))
    ):
        return ServiceUnavailableError(
            "Google authentication is temporarily unavailable while refreshing "
            "Application Default Credentials."
        )
    if isinstance(exc, DefaultCredentialsError):
        return AuthenticationError(
            "Google Application Default Credentials were not found. "
            "Run `gcloud auth application-default login`, set "
            "GOOGLE_APPLICATION_CREDENTIALS, or attach a service account."
        )
    return AuthenticationError(
        "Google Application Default Credentials could not be refreshed. "
        "Reauthenticate with `gcloud auth application-default login` or check "
        "the configured service account."
    )


class VertexAIAuth(httpx.Auth):
    """httpx auth flow that injects a refreshed Google ADC bearer token per request."""

    def __init__(self, token_provider: GoogleAccessTokenProvider, project_id: str):
        self._token_provider = token_provider
        self._project_id = project_id

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        token = await self._token_provider.get_token()
        request.headers["Authorization"] = f"Bearer {token}"
        request.headers["x-goog-user-project"] = self._project_id
        yield request
