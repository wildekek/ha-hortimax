"""Connectivity binary sensor per greenhouse controller."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HortimaxConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import HortimaxCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HortimaxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one connectivity sensor per controller."""
    coordinator = entry.runtime_data
    async_add_entities(
        HortimaxOnlineSensor(coordinator, device_id) for device_id in coordinator.data
    )


class HortimaxOnlineSensor(CoordinatorEntity[HortimaxCoordinator], BinarySensorEntity):
    """Whether the greenhouse controller is online in the HortOS cloud."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: HortimaxCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}::online"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=coordinator.device_labels.get(device_id),
            manufacturer=MANUFACTURER,
        )

    @property
    def _health(self) -> dict[str, Any]:
        device_data = self.coordinator.data.get(self._device_id)
        return device_data.health if device_data else {}

    @property
    def available(self) -> bool:
        return super().available and bool(self._health)

    @property
    def is_on(self) -> bool | None:
        status = self._health.get("onlineStatus")
        if status is None:
            return None
        return status == "Online"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        health = self._health
        return {
            "readout_status": health.get("readoutStatus"),
            "readouts_out_of_sync": health.get("readoutsOutOfSync"),
            "last_device_update": health.get("lastDeviceUpdateTimeUTC"),
        }
