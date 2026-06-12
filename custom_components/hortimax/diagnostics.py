"""Diagnostics for the Ridder HortiMaX Pro (HortOS) integration."""

from __future__ import annotations

import dataclasses
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from . import HortimaxConfigEntry

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HortimaxConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "devices": {
            device_id: {
                "health": device_data.health,
                "readouts": [
                    dataclasses.asdict(readout)
                    for readout in device_data.readouts.values()
                ],
            }
            for device_id, device_data in coordinator.data.items()
        },
    }
