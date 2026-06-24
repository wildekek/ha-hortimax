# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant **custom integration** (`custom_components/hortimax`, domain `hortimax`) for Ridder greenhouse controllers via the **HortOS Automation API**. It is strictly **read-only**: every controller readout becomes a sensor; setpoints are never written. `iot_class` is `cloud_polling`, `integration_type` is `hub`.

## Development environment

Development runs against a **local Home Assistant instance on this machine**, not a hosted one:

- Start it: `.venv/bin/hass -c ha-config` (serves http://localhost:8123). It runs in the foreground; background it when you need the shell back.
- The integration is symlinked into the test config: `ha-config/custom_components/hortimax -> custom_components/hortimax`. Editing the source edits what HA loads; restart HA to pick up code changes.
- `ha-config/` is gitignored — it holds the live config and the **real API key** in `ha-config/.storage/`. A `hortimax` config entry already exists there from onboarding.
- Python 3.14, Home Assistant 2026.6.x, all in `.venv`.

**Do not use the `de Hortus` or `Aruba Rob` Home Assistant MCP servers to inspect or change this integration.** Those are unrelated hosted instances. The integration under development lives only on the local `localhost:8123` instance above; use the HA UI or its REST API there.

To read live state, use the REST API with a long-lived token kept in `ha-config/.ha_token` (gitignored); never echo the token. Example:
`curl -s -H "Authorization: Bearer $(cat ha-config/.ha_token)" http://localhost:8123/api/states/<entity_id>`
The recorder DB (`ha-config/home-assistant_v2.db`) is a fallback when HA is down.

There is no supervisor, so the `homeassistant.restart` service just stops the process — it does not come back. To load code changes, kill `hass` and relaunch it yourself (a config-entry *reload* reuses the already-imported module and will not pick up code edits).

`ha-config/configuration.yaml` has `default_config` expanded manually with `bluetooth`/`usb` omitted, and `aioesphomeapi` is pip-installed into the venv — both to silence unrelated Bluetooth/USB/ESPHome load errors in this dev venv. Don't reintroduce bare `default_config:` without that package present.

## Commands

- Run HA: `.venv/bin/hass -c ha-config`
- Validate config without starting: `.venv/bin/hass -c ha-config --script check_config`
- API smoke test (standalone, no pytest — spins up a fake HortOS server with aiohttp): `.venv/bin/python tests/smoke_api.py`
- Sensor logic test (standalone): `.venv/bin/python tests/smoke_sensor.py`

There is no configured linter, formatter, or pytest suite. Tests are standalone scripts run directly with `.venv/bin/python tests/<file>.py`; each prints `OK ...` lines and a final all-passed message, and asserts inline. Follow that pattern for new tests rather than introducing pytest.

## API reference

Ridder's **Swagger UI** at <https://hortos.ridder.com/api/process-control/index.html> is the source of truth for the HortOS API. The underlying OpenAPI spec is at `{base_url}/v1/swagger.json` (note: *not* the conventional `/swagger/v1/swagger.json`, which 403s), and it is **bearer-auth gated** — fetch it with a token, not anonymously. `api.py`'s module docstring summarises the auth model. Key facts: API-key auth at `/v1/auth/apikey` returns a bearer token (15 min) plus refresh token (7 days); rate limit is 100 requests per 15 seconds per key. The integration spends one request per poll plus one per controller.

The spec confirms there is no enumeration / code-to-label endpoint and that `readoutValueType` is only `Double` or `String`, so the enum-coded Scalars (below) cannot be decoded via the API.

### Hard-won API facts (don't rediscover)

- Real unit identifiers differ from the Swagger examples: `DegreeCelsius` (singular), `Percent`, `Scalar`, `Second`, `Minute`, `Gram/Kilogram`, `Joule/SquareCentimeter`, `Liter/Minute`, `Liter/SquareMeter`, `KilowattHour`, `Watt/SquareMeter`, `Meter/Second`, `CubicMeter`.
- The `quantity` field in definitions is generic (`Ratio`, `Mass/Mass`, …) — useless for device classes; map from unit + readout identifier instead (see `UNIT_MAP` / `_describe()`).
- Readout identifiers follow `<CamelCaseSubject>-<Measured|Calculated|ActualSetting>`, plus one Ridder typo: `IrrigationVolume-Measuered`.
- The API's display `name` embeds the source's userDefinedName (sometimes with trailing whitespace) — don't use it for entity names; `naming.py` derives names from the identifier instead.
- Unchanged readouts update at most every 5 minutes, so polling faster gains nothing.

## Architecture

Data flows in one direction: `HortimaxApiClient` (api.py) → `HortimaxCoordinator` (coordinator.py) → entities (sensor.py, binary_sensor.py). One config entry per organisation; `entry.runtime_data` holds the coordinator.

- **api.py** — async HortOS client. Manages the token pair, auto-refreshes, and re-authenticates once on a 401. Endpoints: device list, device health, latest readouts per device.
- **coordinator.py** — each interval, fetches health plus latest readouts for every device and parses them into `HortimaxReadout` dataclasses (see `_parse_readout` / `_latest_value`). Tracks all source types ever seen (for the options flow) and filters out source types the user excluded.
- **sensor.py / binary_sensor.py** — one sensor per readout; a connectivity binary sensor per controller. New readouts that appear after setup are added automatically via a coordinator listener.

### Device / entity model (the `::` key scheme is load-bearing)

HortOS data is two levels deep — controllers, then *sources* within them (weather station, ventilation group, valve group, …). That maps to:

- One HA **device per controller**, identifier `{device}`.
- One HA **device per source**, identifier `{device}::{sourceType}::{sourceName}`, linked to its controller via `via_device`. Created lazily from sensor `device_info`.
- One **sensor per readout**, unique_id `{device}::{sourceType}::{sourceName}::{readout}`.
- The controller's connectivity sensor uses `{device}::online`.

`_async_remove_excluded_sources` in `__init__.py` parses these unique_ids/identifiers by splitting on `::` and counting parts (≥4 = readout entity, ≥3 = source device) to prune entities/devices for deselected source types. Changing the separator or the segment layout breaks that pruning — keep them in sync.

### Unit and value mapping

`const.py` holds the mapping tables; `sensor.py:_describe()` applies them to derive (unit, device class, state class, display precision) per readout:

- `UNIT_MAP` — HortOS unit identifier (e.g. `DegreeCelsius`, `Watt/SquareMeter`) → HA unit. Unknown identifiers fall back to the raw string **with no device class** (HA rejects a value whose unit doesn't match its device class).
- `DIMENSIONLESS_UNITS` (`Scalar`, `None`) — status/override codes; no unit, no state class, integer display, so they don't pollute long-term statistics.
- `UNIT_DEVICE_CLASS` covers classes that follow purely from the unit. Cases that also need the readout identifier — humidity, wind vs. generic speed, gas, energy/gas daily totals — are decided inline in `_describe()`.
- `UNIT_PRECISION` is display-only; recorded states keep full precision (the API emits float32-converted doubles).

Per-readout special cases keyed by the lowercased identifier subject (`_readout_subject()`, the part before the `-kind` suffix) are also handled in `_describe()` / `native_value`: `TIME_OF_DAY_READOUTS` (sunrise/sunset, seconds-since-local-midnight → `timestamp`) and `WIND_DIRECTION_SUBJECT` (see below).

**Convention:** once a readout's meaning is understood, give it a proper `device_class` (which provides an automatic icon) and/or an explicit `icon` in `READOUT_ICONS`. A sensor that renders with **no icon** (no device class, no icon override) marks a readout that is still unclassified and worth investigating — treat icon-less sensors as the TODO list. Such sensors are also registered **disabled by default** (`_attr_entity_registry_enabled_default = False` in the sensor `__init__`), so classifying one (device class or icon) is what enables it on new installs.

### Enum-coded Scalar readouts (gotcha)

Some readouts come through with `unitIdentifier: "Scalar"` and a `Double` value, but the number is **not a measurement** — it is an enumeration member id from a HortOS table the API does not expose (the readout definition's `min`/`max` are null and there is no enumeration endpoint in the API; the official app resolves the labels). They surface as a meaningless large integer (e.g. ~8780s).

`CardinalWindDirection-Measured` is the one decoded so far: over a day it took exactly the 16 contiguous codes 8772–8787 (the 16-point compass), and two readings cross-checked against the official app (8782=SW, 8783=WSW) anchored 8772 = N, clockwise in 22.5° steps. It is mapped to a `wind_direction` degrees sensor (`measurement_angle` state class) via the `WIND_DIRECTION_*` constants in `const.py`; only `WIND_DIRECTION_CODE_NORTH` would change if a controller used a different id base.

`WeatherStatus-Measured` is the same kind of enum code (seen ~8789) but is **undecoded** — there is no known source for its code→label table (not in the app UI or the docs), so it is intentionally left as the raw scalar. To decode a future one, pull ~24h of history for the readout (`GET /v1/readouts/device/{dev}/values/{id}/{sourceName}/{sourceType}/{start}/{end}`, max 24h window, response under a `readouts` wrapper) to find the contiguous code range, then anchor at least two codes against a known reference.

### Naming

`naming.py` turns CamelCase HortOS identifiers (`VentPositionLeewardSide-Measured`) into friendly names, dropping the default `Measured` kind and parenthesising others. `disambiguate_source_names` resolves clashing source display names by appending the prettified source type, then a trailing number from the technical name if still ambiguous.
