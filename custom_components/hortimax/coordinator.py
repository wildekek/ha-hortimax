"""Data update coordinator for the Ridder HortiMaX Pro (HortOS) integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import HortimaxApiClient, HortimaxApiError, HortimaxAuthError
from .const import CONF_SOURCE_TYPES, DEFAULT_SCAN_INTERVAL, DOMAIN
from .naming import disambiguate_source_names

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class HortimaxReadout:
    """The latest state of a single readout."""

    key: str
    identifier: str
    name: str
    value_type: str  # "Double" or "String"
    unit: str | None
    source_key: str
    source_name: str
    source_type: str
    user_defined_name: str | None
    source_groups: list[str]
    value: float | str | None
    timestamp: datetime | None


@dataclass(slots=True)
class HortimaxDeviceData:
    """All data for one greenhouse controller."""

    identifier: str
    health: dict[str, Any] = field(default_factory=dict)
    readouts: dict[str, HortimaxReadout] = field(default_factory=dict)
    # source key -> de-duplicated display name
    source_names: dict[str, str] = field(default_factory=dict)


def source_key(source_type: str, source_name: str) -> str:
    """Stable key for a source within a device."""
    return f"{source_type}::{source_name}"


def readout_key(source_type: str, source_name: str, identifier: str) -> str:
    """Stable key for a readout within a device."""
    return f"{source_type}::{source_name}::{identifier}"


class HortimaxCoordinator(DataUpdateCoordinator[dict[str, HortimaxDeviceData]]):
    """Polls device health and latest readout values for all devices."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: HortimaxApiClient,
    ) -> None:
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.device_names: list[str] = []
        # Device identifier -> friendly label from /v1/devices/info.
        self.device_labels: dict[str, str] = {}
        # Source types selected in the options; empty set means all.
        self.selected_source_types: set[str] = set(
            entry.options.get(CONF_SOURCE_TYPES) or []
        )
        # All source types ever seen (unfiltered), for the options flow.
        self.all_source_types: set[str] = set()

    async def _async_setup(self) -> None:
        """Discover the available devices once."""
        try:
            self.device_names = await self.client.async_get_device_names()
        except HortimaxAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HortimaxApiError as err:
            raise UpdateFailed(f"Error setting up HortOS API: {err}") from err

        # Friendly labels are cosmetic; tolerate this call failing.
        try:
            self.device_labels = {
                name: label
                for item in await self.client.async_get_devices_info()
                if (name := item.get("name")) and (label := item.get("label"))
            }
        except HortimaxApiError as err:
            _LOGGER.debug("Could not fetch device info for labels: %s", err)

    async def _async_update_data(self) -> dict[str, HortimaxDeviceData]:
        try:
            health_by_name = {
                item.get("name"): item
                for item in await self.client.async_get_devices_health()
            }
            data: dict[str, HortimaxDeviceData] = {}
            for device in self.device_names:
                device_data = HortimaxDeviceData(
                    identifier=device, health=health_by_name.get(device, {})
                )
                latest = await self.client.async_get_latest_readouts(device)
                sources: dict[str, tuple[str, str, str]] = {}
                for raw in latest.get("readouts", []):
                    readout = _parse_readout(raw)
                    if readout is None:
                        continue
                    self.all_source_types.add(readout.source_type)
                    if (
                        self.selected_source_types
                        and readout.source_type not in self.selected_source_types
                    ):
                        continue
                    device_data.readouts[readout.key] = readout
                    sources[readout.source_key] = (
                        readout.user_defined_name or readout.source_name,
                        readout.source_type,
                        readout.source_name,
                    )
                device_data.source_names = disambiguate_source_names(sources)
                data[device] = device_data
        except HortimaxAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HortimaxApiError as err:
            raise UpdateFailed(f"Error fetching HortOS data: {err}") from err
        return data


def _parse_readout(raw: dict[str, Any]) -> HortimaxReadout | None:
    source = raw.get("source") or {}
    identifier = raw.get("readoutIdentifier")
    if not identifier:
        return None
    # Source names from the API can carry stray whitespace.
    source_name = (source.get("sourceName") or "").strip()
    source_type = (source.get("sourceType") or "").strip()
    user_defined = (source.get("userDefinedName") or "").strip() or None
    value, timestamp = _latest_value(raw.get("values") or [])
    return HortimaxReadout(
        key=readout_key(source_type, source_name, identifier),
        identifier=identifier,
        name=(raw.get("name") or identifier).strip(),
        value_type=raw.get("readoutValueType", "Double"),
        unit=raw.get("unitIdentifier"),
        source_key=source_key(source_type, source_name),
        source_name=source_name,
        source_type=source_type,
        user_defined_name=user_defined,
        source_groups=source.get("sourceGroups") or [],
        value=value,
        timestamp=timestamp,
    )


def _latest_value(
    values: list[dict[str, Any]],
) -> tuple[float | str | None, datetime | None]:
    """Pick the most recent entry from a readout's value list."""
    latest_value: float | str | None = None
    latest_ts: datetime | None = None
    for item in values:
        ts = dt_util.parse_datetime(item.get("timestampUTC") or "")
        if ts is None:
            continue
        ts = dt_util.as_utc(ts)
        if latest_ts is None or ts > latest_ts:
            latest_ts = ts
            value = item.get("value")
            # Doubles and strings come through as-is; anything else
            # (unexpected objects) is treated as unknown.
            latest_value = value if isinstance(value, (int, float, str)) else None
    return latest_value, latest_ts
