"""Sensors for every HortOS readout."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import DEGREE, EntityCategory, UnitOfSpeed, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import HortimaxConfigEntry
from .const import (
    DIMENSIONLESS_UNITS,
    DOMAIN,
    MANUFACTURER,
    READOUT_ICONS,
    TIME_OF_DAY_READOUTS,
    UNIT_DEVICE_CLASS,
    UNIT_MAP,
    UNIT_PRECISION,
    WIND_DIRECTION_CODE_NORTH,
    WIND_DIRECTION_SECTORS,
    WIND_DIRECTION_STEP_DEGREES,
    WIND_DIRECTION_SUBJECT,
)
from .coordinator import HortimaxCoordinator, HortimaxReadout
from .naming import readout_display_name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HortimaxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one sensor per readout, adding new ones as they appear."""
    coordinator = entry.runtime_data
    known: set[tuple[str, str]] = set()

    @callback
    def _add_new_entities() -> None:
        new_entities: list[HortimaxReadoutSensor] = []
        for device_id, device_data in coordinator.data.items():
            for key in device_data.readouts:
                if (device_id, key) in known:
                    continue
                known.add((device_id, key))
                new_entities.append(
                    HortimaxReadoutSensor(coordinator, device_id, key)
                )
        if new_entities:
            async_add_entities(new_entities)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


def _readout_subject(identifier: str) -> str:
    """The identifier minus its '-kind' suffix, lowercased (see naming.py)."""
    return identifier.partition("-")[0].lower()


def _describe(
    readout: HortimaxReadout,
) -> tuple[
    str | None, SensorDeviceClass | None, SensorStateClass | None, int | None
]:
    """Derive (unit, device class, state class, display precision).

    Device classes are only assigned for units we mapped to a Home Assistant
    unit; an unmapped raw unit with a device class would make HA reject the
    value. Dimensionless readouts (Scalar) are status/override codes, which
    would pollute long-term statistics, so they get no state class — and
    integer display, as their values are codes like 6561.
    """
    if readout.value_type != "Double":
        return None, None, None, None
    subject = _readout_subject(readout.identifier)
    # Seconds-since-midnight readouts are surfaced as timestamps; native_value
    # turns the second count into today's datetime.
    if subject in TIME_OF_DAY_READOUTS:
        return None, SensorDeviceClass.TIMESTAMP, None, None
    # CardinalWindDirection is an enum code; native_value turns it into a
    # bearing in degrees (statistics use the circular mean for this class).
    if subject == WIND_DIRECTION_SUBJECT:
        return (
            DEGREE,
            SensorDeviceClass.WIND_DIRECTION,
            SensorStateClass.MEASUREMENT_ANGLE,
            None,
        )
    raw_unit = readout.unit
    if not raw_unit or raw_unit in DIMENSIONLESS_UNITS:
        return None, None, None, 0

    unit = UNIT_MAP.get(raw_unit)
    mapped = unit is not None
    if unit is None:
        unit = raw_unit  # truthful fallback, but no device class
    precision = UNIT_PRECISION.get(unit, 0) if mapped else 0

    identifier = readout.identifier.lower()
    device_class: SensorDeviceClass | None = None
    if mapped:
        device_class = UNIT_DEVICE_CLASS.get(unit)
        if device_class is None:
            if unit == "%" and "relativehumidity" in identifier:
                device_class = SensorDeviceClass.HUMIDITY
            elif unit == UnitOfSpeed.METERS_PER_SECOND:
                device_class = (
                    SensorDeviceClass.WIND_SPEED
                    if "wind" in identifier
                    else SensorDeviceClass.SPEED
                )
            elif (
                unit == UnitOfVolume.CUBIC_METERS
                and readout.source_type == "GasMeter"
            ):
                device_class = SensorDeviceClass.GAS

    # Daily consumption counters (electricity/gas meters) reset at midnight,
    # which TOTAL_INCREASING handles; this also feeds the Energy dashboard.
    if "consumptiontoday" in identifier and device_class in (
        SensorDeviceClass.ENERGY,
        SensorDeviceClass.GAS,
    ):
        state_class = SensorStateClass.TOTAL_INCREASING
    else:
        state_class = SensorStateClass.MEASUREMENT

    return unit, device_class, state_class, precision


class HortimaxReadoutSensor(CoordinatorEntity[HortimaxCoordinator], SensorEntity):
    """A single readout (measurement) from a HortOS source."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: HortimaxCoordinator, device_id: str, key: str
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._key = key
        readout = self._readout
        assert readout is not None

        self._attr_unique_id = f"{device_id}::{key}"
        self._attr_name = readout_display_name(readout.identifier)
        self._attr_icon = READOUT_ICONS.get(_readout_subject(readout.identifier))
        # Static settings readouts go to the diagnostic section so the
        # actual measurements stand out on the device page.
        if readout.identifier.lower().endswith("-actualsetting"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Each HortOS source (weather station, ventilation group, valve
        # group, ...) becomes its own HA device under the controller.
        device_data = coordinator.data[device_id]
        source_display = device_data.source_names.get(
            readout.source_key, readout.user_defined_name or readout.source_name
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{device_id}::{readout.source_key}")},
            name=source_display,
            model=readout.source_type,
            manufacturer=MANUFACTURER,
            via_device=(DOMAIN, device_id),
        )

        (
            self._attr_native_unit_of_measurement,
            self._attr_device_class,
            self._attr_state_class,
            self._attr_suggested_display_precision,
        ) = _describe(readout)

    @property
    def _readout(self) -> HortimaxReadout | None:
        device_data = self.coordinator.data.get(self._device_id)
        if device_data is None:
            return None
        return device_data.readouts.get(self._key)

    @property
    def available(self) -> bool:
        return super().available and self._readout is not None

    @property
    def native_value(self) -> float | str | datetime | None:
        readout = self._readout
        if readout is None or readout.value is None:
            return None
        if readout.value_type == "Double":
            try:
                number = float(readout.value)
            except (TypeError, ValueError):
                return None
            subject = _readout_subject(readout.identifier)
            if subject in TIME_OF_DAY_READOUTS:
                # Seconds since local midnight -> today's timestamp.
                return dt_util.start_of_local_day() + timedelta(seconds=number)
            if subject == WIND_DIRECTION_SUBJECT:
                # Enum code -> compass bearing in degrees.
                sector = (round(number) - WIND_DIRECTION_CODE_NORTH) % (
                    WIND_DIRECTION_SECTORS
                )
                return sector * WIND_DIRECTION_STEP_DEGREES
            return number
        return str(readout.value)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        readout = self._readout
        if readout is None:
            return None
        return {
            "measured_at": readout.timestamp.isoformat()
            if readout.timestamp
            else None,
            "readout_identifier": readout.identifier,
            "readout_name": readout.name,
            "source_groups": readout.source_groups,
        }
