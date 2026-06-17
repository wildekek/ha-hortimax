"""Standalone unit test for the sensor description / value logic.

Run with: .venv/bin/python tests/smoke_sensor.py

Covers the seconds-since-midnight -> timestamp conversion for sunrise/sunset
readouts, plus a regular measurement as a regression guard.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sys

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import DEGREE, UnitOfTemperature
from homeassistant.util import dt as dt_util

sys.path.insert(0, ".")

from custom_components.hortimax.coordinator import (  # noqa: E402
    HortimaxDeviceData,
    HortimaxReadout,
    readout_key,
    source_key,
)
from custom_components.hortimax.sensor import (  # noqa: E402
    HortimaxReadoutSensor,
    _describe,
    _readout_subject,
)

DEVICE_ID = "HOR10805485.627"


class FakeCoordinator:
    """Minimal stand-in for HortimaxCoordinator (only `.data` is read)."""

    def __init__(self, data: dict[str, HortimaxDeviceData]) -> None:
        self.data = data
        self.last_update_success = True


def _readout(
    *,
    identifier: str,
    value: float | str,
    value_type: str = "Double",
    unit: str | None = None,
    source_type: str = "System",
    source_name: str = "System",
) -> HortimaxReadout:
    return HortimaxReadout(
        key=readout_key(source_type, source_name, identifier),
        identifier=identifier,
        name=identifier,
        value_type=value_type,
        unit=unit,
        source_key=source_key(source_type, source_name),
        source_name=source_name,
        source_type=source_type,
        user_defined_name=None,
        source_groups=[source_type],
        value=value,
        timestamp=datetime(2026, 6, 17, 19, 55, tzinfo=timezone.utc),
    )


def _build_sensor(readout: HortimaxReadout) -> HortimaxReadoutSensor:
    device_data = HortimaxDeviceData(
        identifier=DEVICE_ID,
        readouts={readout.key: readout},
        source_names={readout.source_key: readout.source_name},
    )
    coordinator = FakeCoordinator({DEVICE_ID: device_data})
    return HortimaxReadoutSensor(coordinator, DEVICE_ID, readout.key)


def main() -> None:
    assert _readout_subject("SunriseToday-Measured") == "sunrisetoday"
    assert _readout_subject("AirTemperature-Measured") == "airtemperature"
    print("OK _readout_subject strips the kind suffix")

    # Sunrise/sunset: seconds since local midnight -> timestamp.
    for identifier, seconds in (
        ("SunriseToday-Measured", 19145.0),
        ("SunsetToday-Measured", 79321.0),
    ):
        readout = _readout(identifier=identifier, value=seconds)
        unit, device_class, state_class, precision = _describe(readout)
        assert device_class is SensorDeviceClass.TIMESTAMP, identifier
        assert unit is None and state_class is None and precision is None
        sensor = _build_sensor(readout)
        assert sensor.device_class is SensorDeviceClass.TIMESTAMP
        expected = dt_util.start_of_local_day() + timedelta(seconds=seconds)
        value = sensor.native_value
        assert isinstance(value, datetime), type(value)
        assert value == expected, (identifier, value, expected)
        print(f"OK {identifier}: {seconds} s -> {value.isoformat()}")

    # CardinalWindDirection: enum code -> compass bearing in degrees.
    for code, expected_deg in (
        (8772, 0.0),     # N
        (8782, 225.0),   # SW
        (8783, 247.5),   # WSW
        (8787, 337.5),   # NNW
    ):
        readout = _readout(
            identifier="CardinalWindDirection-Measured",
            value=float(code),
            source_type="WeatherStation",
            source_name="Weather station 001",
        )
        unit, device_class, state_class, _ = _describe(readout)
        assert unit == DEGREE
        assert device_class is SensorDeviceClass.WIND_DIRECTION
        assert state_class is SensorStateClass.MEASUREMENT_ANGLE
        sensor = _build_sensor(readout)
        assert sensor.native_value == expected_deg, (code, sensor.native_value)
        print(f"OK CardinalWindDirection {code} -> {expected_deg}°")

    # Regression: a regular mapped measurement is unaffected.
    temp = _readout(
        identifier="AirTemperature-Measured",
        value=21.345,
        unit="DegreeCelsius",
    )
    unit, device_class, state_class, precision = _describe(temp)
    assert unit == UnitOfTemperature.CELSIUS
    assert device_class is SensorDeviceClass.TEMPERATURE
    assert state_class is SensorStateClass.MEASUREMENT
    sensor = _build_sensor(temp)
    assert sensor.native_value == 21.345
    print("OK AirTemperature stays a numeric temperature measurement")

    # Unclassified readouts (no device class, no icon) are disabled by default;
    # classified ones (device class or icon) stay enabled.
    override = _readout(identifier="Override-Measured", value=6561.0, unit="Scalar")
    override_sensor = _build_sensor(override)
    assert override_sensor.device_class is None and override_sensor.icon is None
    assert override_sensor.entity_registry_enabled_default is False
    assert _build_sensor(temp).entity_registry_enabled_default is True
    abs_hum = _readout(
        identifier="AbsoluteHumidity-Measured", value=10.0, unit="Gram/Kilogram"
    )
    assert _build_sensor(abs_hum).entity_registry_enabled_default is True
    print("OK unclassified readouts are disabled by default")

    print("\nAll sensor smoke tests passed.")


if __name__ == "__main__":
    main()
