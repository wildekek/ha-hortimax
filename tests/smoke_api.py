"""Standalone smoke test for HortimaxApiClient against a fake HortOS server.

Run with: .venv/bin/python tests/smoke_api.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import sys

import aiohttp
from aiohttp import web

sys.path.insert(0, ".")

from custom_components.hortimax.api import (  # noqa: E402
    HortimaxApiClient,
    HortimaxAuthError,
)
from custom_components.hortimax.coordinator import _latest_value  # noqa: E402

API_KEY = "test-key"
state = {"auth_calls": 0, "refresh_calls": 0, "expire_immediately": False}


def _tokens(n: int) -> dict:
    expire = datetime.now(timezone.utc) + (
        timedelta(seconds=-1) if state["expire_immediately"] else timedelta(minutes=15)
    )
    return {
        "organisation": {"id": 42, "href": "/org/42"},
        "token": f"tok-{n}",
        "expireTime": expire.isoformat().replace("+00:00", "Z"),
        "refreshToken": {
            "token": f"refresh-{n}",
            "expireTime": (
                datetime.now(timezone.utc) + timedelta(days=7)
            ).isoformat().replace("+00:00", "Z"),
        },
    }


async def auth(request: web.Request) -> web.Response:
    body = await request.json()
    if body.get("apikey") != API_KEY:
        return web.Response(status=401)
    state["auth_calls"] += 1
    return web.json_response(_tokens(state["auth_calls"]))


async def refresh(request: web.Request) -> web.Response:
    body = await request.json()
    assert "token" in body and "refreshToken" in body
    state["refresh_calls"] += 1
    return web.json_response(_tokens(100 + state["refresh_calls"]))


def _require_bearer(request: web.Request) -> web.Response | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer tok-") and not auth_header.startswith(
        "Bearer refreshed"
    ):
        return web.Response(status=401)
    return None


async def devices(request: web.Request) -> web.Response:
    if err := _require_bearer(request):
        return err
    return web.json_response(["HOR10805485.627"])


async def health(request: web.Request) -> web.Response:
    if err := _require_bearer(request):
        return err
    return web.json_response(
        [
            {
                "publicId": "pid",
                "name": "HOR10805485.627",
                "label": "De Hortus Multima",
                "lastDeviceUpdateTimeUTC": "2026-06-12T08:00:00.000Z",
                "onlineStatus": "Online",
                "readoutStatus": "Healthy",
                "readoutsOutOfSync": [],
            }
        ]
    )


async def definitions(request: web.Request) -> web.Response:
    if err := _require_bearer(request):
        return err
    return web.json_response(
        [
            {
                "name": "Outside temperature",
                "readoutIdentifier": "OutsideTemp",
                "readoutValueType": "Double",
                "quantity": "Temperature",
                "source": {
                    "sourceName": "Weather station 001",
                    "sourceType": "WeatherStation",
                    "userDefinedName": "Weerstation",
                    "sourceGroups": ["Weather"],
                },
                "min": -50.0,
                "max": 60.0,
            }
        ]
    )


async def latest(request: web.Request) -> web.Response:
    if err := _require_bearer(request):
        return err
    return web.json_response(
        {
            "readouts": [
                {
                    "name": "Outside temperature",
                    "readoutIdentifier": "OutsideTemp",
                    "readoutValueType": "Double",
                    "unitIdentifier": "DegreesCelsius",
                    "device": "HOR10805485.627",
                    "source": {
                        "sourceName": "Weather station 001",
                        "sourceType": "WeatherStation",
                        "userDefinedName": "Weerstation",
                        "sourceGroups": ["Weather"],
                    },
                    "values": [
                        {"timestampUTC": "2026-06-12T07:55:00Z", "value": 17.9},
                        {"timestampUTC": "2026-06-12T08:00:00Z", "value": 18.2},
                    ],
                },
                {
                    "name": "Screen status",
                    "readoutIdentifier": "ScreenStatus",
                    "readoutValueType": "String",
                    "unitIdentifier": None,
                    "device": "HOR10805485.627",
                    "source": {
                        "sourceName": "Screen 1",
                        "sourceType": "Screen",
                        "userDefinedName": None,
                        "sourceGroups": [],
                    },
                    "values": [
                        {"timestampUTC": "2026-06-12T08:00:00Z", "value": "Closed"}
                    ],
                },
            ]
        }
    )


async def main() -> None:
    app = web.Application()
    app.router.add_post("/v1/auth/apikey", auth)
    app.router.add_post("/v1/token/refresh", refresh)
    app.router.add_get("/v1/devices", devices)
    app.router.add_get("/v1/devices/health", health)
    app.router.add_get(
        "/v1/definitions/readout/device/{device}", definitions
    )
    app.router.add_get("/v1/readouts/device/{device}/values/latest", latest)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    base = f"http://127.0.0.1:{port}"

    async with aiohttp.ClientSession() as session:
        # Wrong API key -> auth error
        bad = HortimaxApiClient(session, "wrong", base)
        try:
            await bad.async_authenticate()
            raise AssertionError("expected HortimaxAuthError")
        except HortimaxAuthError:
            print("OK invalid key raises HortimaxAuthError")

        client = HortimaxApiClient(session, API_KEY, base)
        auth_data = await client.async_authenticate()
        assert auth_data["organisation"]["id"] == 42
        print("OK authenticate")

        names = await client.async_get_device_names()
        assert names == ["HOR10805485.627"]
        print("OK devices:", names)

        health_data = await client.async_get_devices_health()
        assert health_data[0]["onlineStatus"] == "Online"
        print("OK health")

        defs = await client.async_get_readout_definitions(names[0])
        assert defs[0]["quantity"] == "Temperature"
        print("OK definitions (URL-quoted device id)")

        readouts = await client.async_get_latest_readouts(names[0])
        assert len(readouts["readouts"]) == 2
        print("OK latest readouts")

        value, ts = _latest_value(readouts["readouts"][0]["values"])
        assert value == 18.2 and ts is not None and ts.hour == 8
        print("OK _latest_value picks newest:", value, ts)

        # Force token expiry -> next call must transparently refresh
        state["expire_immediately"] = True
        await client.async_authenticate()  # store an already-expired token
        state["expire_immediately"] = False
        before = state["refresh_calls"]
        await client.async_get_device_names()
        assert state["refresh_calls"] == before + 1
        print("OK expired token triggers /v1/token/refresh")

    await runner.cleanup()
    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
