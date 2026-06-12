"""The Ridder HortiMaX Pro (HortOS) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HortimaxApiClient
from .const import (
    CONF_BASE_URL,
    CONF_SOURCE_TYPES,
    DEFAULT_BASE_URL,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import HortimaxCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type HortimaxConfigEntry = ConfigEntry[HortimaxCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: HortimaxConfigEntry) -> bool:
    """Set up Ridder HortiMaX Pro from a config entry."""
    client = HortimaxApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_API_KEY],
        entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
    )
    coordinator = HortimaxCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _async_remove_excluded_sources(hass, entry)

    # Register the greenhouse controllers up front so source devices can
    # reference them through via_device.
    device_registry = dr.async_get(hass)
    for identifier, device_data in coordinator.data.items():
        health = device_data.health
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, identifier)},
            manufacturer=MANUFACTURER,
            name=health.get("label") or health.get("name") or identifier,
            model="Greenhouse controller",
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _async_remove_excluded_sources(
    hass: HomeAssistant, entry: HortimaxConfigEntry
) -> None:
    """Drop registry entities/devices for source types excluded in options.

    Unique IDs are '{device}::{sourceType}::{sourceName}::{readout}' and
    source device identifiers '{device}::{sourceType}::{sourceName}'; the
    controller device ('{device}') and its connectivity sensor
    ('{device}::online') never match and are always kept.
    """
    selected = set(entry.options.get(CONF_SOURCE_TYPES) or [])
    if not selected:
        return
    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        parts = entity.unique_id.split("::")
        if len(parts) >= 4 and parts[1] not in selected:
            entity_registry.async_remove(entity.entity_id)
    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        for domain, identifier in device.identifiers:
            if domain != DOMAIN:
                continue
            parts = identifier.split("::")
            if len(parts) >= 3 and parts[1] not in selected:
                device_registry.async_update_device(
                    device.id, remove_config_entry_id=entry.entry_id
                )


async def _async_update_listener(
    hass: HomeAssistant, entry: HortimaxConfigEntry
) -> None:
    """Reload the entry when options (e.g. scan interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HortimaxConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
