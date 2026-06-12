"""Async client for the Ridder HortOS Automation API.

Authentication model (per the official Postman collection):
- POST /v1/auth/apikey with the API key returns a bearer token (valid 15
  minutes) and a refresh token (valid 7 days).
- POST /v1/token/refresh exchanges an expired bearer token + refresh token
  for a fresh pair.
- The API allows at most 100 requests per 15 seconds per API key.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import aiohttp

from homeassistant.util import dt as dt_util

from .const import DEFAULT_BASE_URL

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
TOKEN_LEEWAY = timedelta(seconds=60)


class HortimaxApiError(Exception):
    """Raised when the HortOS API returns an error or is unreachable."""


class HortimaxAuthError(HortimaxApiError):
    """Raised when authentication with the HortOS API fails."""


class HortimaxApiClient:
    """Minimal async client for the read-only parts of the HortOS API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._token_expires: datetime | None = None
        self._refresh_token: str | None = None
        self._refresh_expires: datetime | None = None
        self._auth_lock = asyncio.Lock()
        self.organisation: dict[str, Any] | None = None

    # ---------------------------------------------------------------- auth

    async def async_authenticate(self) -> dict[str, Any]:
        """Authenticate with the API key and store the token pair."""
        data = await self._raw_post_json(
            "/v1/auth/apikey", {"apikey": self._api_key}
        )
        self._store_tokens(data)
        return data

    async def _async_refresh_tokens(self) -> None:
        data = await self._raw_post_json(
            "/v1/token/refresh",
            {"token": self._token, "refreshToken": self._refresh_token},
        )
        self._store_tokens(data)

    def _store_tokens(self, data: dict[str, Any]) -> None:
        try:
            self._token = data["token"]
            self._token_expires = _parse_utc(data["expireTime"])
            refresh = data["refreshToken"]
            self._refresh_token = refresh["token"]
            self._refresh_expires = _parse_utc(refresh["expireTime"])
        except (KeyError, TypeError) as err:
            raise HortimaxApiError(
                f"Unexpected authentication response: {data}"
            ) from err
        self.organisation = data.get("organisation")

    def _token_valid(self, expires: datetime | None) -> bool:
        return expires is not None and dt_util.utcnow() + TOKEN_LEEWAY < expires

    async def _async_ensure_token(self, *, force: bool = False) -> str:
        async with self._auth_lock:
            if not force and self._token and self._token_valid(self._token_expires):
                return self._token
            if self._refresh_token and self._token_valid(self._refresh_expires):
                try:
                    await self._async_refresh_tokens()
                except HortimaxApiError:
                    await self.async_authenticate()
            else:
                await self.async_authenticate()
            assert self._token is not None
            return self._token

    # ------------------------------------------------------------ requests

    async def _raw_post_json(self, path: str, payload: dict[str, Any]) -> Any:
        """POST without bearer auth (used for the auth endpoints)."""
        try:
            async with self._session.post(
                f"{self._base_url}{path}", json=payload, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise HortimaxAuthError(
                        f"Authentication rejected by {path} (HTTP {resp.status})"
                    )
                if resp.status >= 400:
                    body = await resp.text()
                    raise HortimaxApiError(
                        f"HTTP {resp.status} from {path}: {body[:200]}"
                    )
                return await resp.json()
        except TimeoutError as err:
            raise HortimaxApiError(f"Timeout calling {path}") from err
        except aiohttp.ClientError as err:
            raise HortimaxApiError(f"Error calling {path}: {err}") from err

    async def _async_get(self, path: str) -> Any:
        """GET with bearer auth, re-authenticating once on a 401."""
        token = await self._async_ensure_token()
        for attempt in (1, 2):
            try:
                async with self._session.get(
                    f"{self._base_url}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=REQUEST_TIMEOUT,
                ) as resp:
                    if resp.status == 401 and attempt == 1:
                        token = await self._async_ensure_token(force=True)
                        continue
                    if resp.status in (401, 403):
                        raise HortimaxAuthError(
                            f"Authorization rejected for {path} (HTTP {resp.status})"
                        )
                    if resp.status >= 400:
                        body = await resp.text()
                        raise HortimaxApiError(
                            f"HTTP {resp.status} from {path}: {body[:200]}"
                        )
                    return await resp.json()
            except TimeoutError as err:
                raise HortimaxApiError(f"Timeout calling {path}") from err
            except aiohttp.ClientError as err:
                raise HortimaxApiError(f"Error calling {path}: {err}") from err
        raise HortimaxApiError(f"Unreachable retry state for {path}")

    # ------------------------------------------------------------ endpoints

    async def async_get_device_names(self) -> list[str]:
        """Return the identifiers of the available devices."""
        return await self._async_get("/v1/devices")

    async def async_get_devices_health(self) -> list[dict[str, Any]]:
        """Return health/online status for all devices."""
        return await self._async_get("/v1/devices/health")

    async def async_get_readout_definitions(
        self, device_identifier: str
    ) -> list[dict[str, Any]]:
        """Return all readout definitions for a device."""
        return await self._async_get(
            f"/v1/definitions/readout/device/{_seg(device_identifier)}"
        )

    async def async_get_latest_readouts(
        self, device_identifier: str
    ) -> dict[str, Any]:
        """Return the latest value of every readout of a device."""
        return await self._async_get(
            f"/v1/readouts/device/{_seg(device_identifier)}/values/latest"
        )


def _seg(value: str) -> str:
    """Quote a value for use as a URL path segment."""
    return quote(value, safe="")


def _parse_utc(value: str) -> datetime:
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        raise HortimaxApiError(f"Invalid datetime in API response: {value}")
    return dt_util.as_utc(parsed)
