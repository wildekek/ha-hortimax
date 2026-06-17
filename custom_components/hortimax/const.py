"""Constants for the Ridder HortiMaX Pro (HortOS) integration."""

from __future__ import annotations

from typing import Final

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    DEGREE,
    LIGHT_LUX,
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfIrradiance,
    UnitOfMass,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)

DOMAIN: Final = "hortimax"
MANUFACTURER: Final = "Ridder"

CONF_BASE_URL: Final = "base_url"
DEFAULT_BASE_URL: Final = "https://hortos.ridder.com/api/process-control"

# Options: list of source types to include; missing or empty means all.
CONF_SOURCE_TYPES: Final = "source_types"

DEFAULT_SCAN_INTERVAL: Final = 60  # seconds
MIN_SCAN_INTERVAL: Final = 15

# Unit identifiers that mean "dimensionless"; such readouts get no unit and
# no statistics (they are mostly status/override codes).
DIMENSIONLESS_UNITS: Final = {"Scalar", "None"}

# Readouts that report a time of day as seconds since (local) midnight, e.g.
# SunriseToday = 19145 -> 05:19. HA renders these far better as a timestamp
# than as a raw second count. Keyed by the lowercased identifier subject
# (the part before the '-kind' suffix, see naming.py).
TIME_OF_DAY_READOUTS: Final[frozenset[str]] = frozenset(
    {"sunrisetoday", "sunsettoday"}
)

# Maps HortOS unit identifiers to Home Assistant units of measurement.
# The first block is the complete set observed on a live HortOS Multima
# installation; the rest are plausible variants kept as aliases. Unknown
# identifiers fall back to the raw identifier string (without device class).
UNIT_MAP: Final[dict[str, str]] = {
    # Observed on a live system
    "Percent": PERCENTAGE,
    "DegreeCelsius": UnitOfTemperature.CELSIUS,
    "Second": UnitOfTime.SECONDS,
    "Minute": UnitOfTime.MINUTES,
    "Gram/Kilogram": "g/kg",
    "Joule/SquareCentimeter": "J/cm²",
    "Liter/Minute": UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
    "Liter/SquareMeter": "l/m²",
    "KilowattHour": UnitOfEnergy.KILO_WATT_HOUR,
    "Watt/SquareMeter": UnitOfIrradiance.WATTS_PER_SQUARE_METER,
    "Meter/Second": UnitOfSpeed.METERS_PER_SECOND,
    "CubicMeter": UnitOfVolume.CUBIC_METERS,
    # Aliases / not yet observed
    "DegreesCelsius": UnitOfTemperature.CELSIUS,
    "DegreeFahrenheit": UnitOfTemperature.FAHRENHEIT,
    "DegreesFahrenheit": UnitOfTemperature.FAHRENHEIT,
    "Kelvin": UnitOfTemperature.KELVIN,
    "Percentage": PERCENTAGE,
    "PartsPerMillion": CONCENTRATION_PARTS_PER_MILLION,
    "Joule/SquareMeter": "J/m²",
    "Kilometer/Hour": UnitOfSpeed.KILOMETERS_PER_HOUR,
    "Degrees": DEGREE,
    "Degree": DEGREE,
    "Liter": UnitOfVolume.LITERS,
    "Milliliter": UnitOfVolume.MILLILITERS,
    "Milliliter/SquareMeter": "ml/m²",
    "CubicMeter/Hour": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "Kilogram": UnitOfMass.KILOGRAMS,
    "Gram": UnitOfMass.GRAMS,
    "Hour": UnitOfTime.HOURS,
    "MilliSiemens/Centimeter": "mS/cm",
    "MicroSiemens/Centimeter": "µS/cm",
    "Ph": "pH",
    "PH": "pH",
    "Bar": UnitOfPressure.BAR,
    "MilliBar": UnitOfPressure.MBAR,
    "HectoPascal": UnitOfPressure.HPA,
    "Pascal": UnitOfPressure.PA,
    "Gram/CubicMeter": "g/m³",
    "Micromol/SquareMeter/Second": "µmol/m²/s",
    "Mol/SquareMeter/Day": "mol/m²/d",
    "Lux": LIGHT_LUX,
    "Watt": UnitOfPower.WATT,
    "Kilowatt": UnitOfPower.KILO_WATT,
}

# Suggested display precision per mapped HA unit. Display-layer only:
# recorded states and statistics keep full precision. The API emits
# float32-converted doubles (e.g. 90.15303039550781 %), so every numeric
# sensor needs a sane default.
UNIT_PRECISION: Final[dict[str, int]] = {
    UnitOfTemperature.CELSIUS: 1,
    UnitOfTemperature.FAHRENHEIT: 1,
    UnitOfTemperature.KELVIN: 1,
    PERCENTAGE: 1,
    "g/kg": 1,
    "g/m³": 1,
    "J/cm²": 1,
    "J/m²": 0,
    UnitOfSpeed.METERS_PER_SECOND: 1,
    UnitOfSpeed.KILOMETERS_PER_HOUR: 1,
    UnitOfVolumeFlowRate.LITERS_PER_MINUTE: 1,
    UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR: 1,
    "l/m²": 1,
    "ml/m²": 0,
    UnitOfEnergy.KILO_WATT_HOUR: 2,
    UnitOfVolume.CUBIC_METERS: 2,
    UnitOfVolume.LITERS: 1,
    UnitOfVolume.MILLILITERS: 0,
    UnitOfTime.SECONDS: 0,
    UnitOfTime.MINUTES: 0,
    UnitOfTime.HOURS: 1,
    UnitOfIrradiance.WATTS_PER_SQUARE_METER: 0,
    CONCENTRATION_PARTS_PER_MILLION: 0,
    LIGHT_LUX: 0,
    "mS/cm": 2,
    "µS/cm": 0,
    "pH": 1,
    UnitOfPressure.BAR: 2,
    UnitOfPressure.MBAR: 0,
    UnitOfPressure.HPA: 0,
    UnitOfPressure.PA: 0,
    "µmol/m²/s": 0,
    "mol/m²/d": 1,
    DEGREE: 0,
    UnitOfPower.WATT: 0,
    UnitOfPower.KILO_WATT: 2,
    UnitOfMass.KILOGRAMS: 1,
    UnitOfMass.GRAMS: 0,
}

# Device classes that follow directly from the (mapped) unit. Cases that
# need the readout identifier as well (humidity, wind, gas, energy) are
# handled in sensor.py.
UNIT_DEVICE_CLASS: Final[dict[str, SensorDeviceClass]] = {
    UnitOfTemperature.CELSIUS: SensorDeviceClass.TEMPERATURE,
    UnitOfTemperature.FAHRENHEIT: SensorDeviceClass.TEMPERATURE,
    UnitOfTemperature.KELVIN: SensorDeviceClass.TEMPERATURE,
    UnitOfIrradiance.WATTS_PER_SQUARE_METER: SensorDeviceClass.IRRADIANCE,
    CONCENTRATION_PARTS_PER_MILLION: SensorDeviceClass.CO2,
    LIGHT_LUX: SensorDeviceClass.ILLUMINANCE,
    UnitOfTime.SECONDS: SensorDeviceClass.DURATION,
    UnitOfTime.MINUTES: SensorDeviceClass.DURATION,
    UnitOfTime.HOURS: SensorDeviceClass.DURATION,
    UnitOfEnergy.KILO_WATT_HOUR: SensorDeviceClass.ENERGY,
    UnitOfPower.WATT: SensorDeviceClass.POWER,
    UnitOfPower.KILO_WATT: SensorDeviceClass.POWER,
}
