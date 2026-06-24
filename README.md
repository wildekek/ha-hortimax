<img src="assets/brands/hortimax/icon.png" alt="HortOS shield" width="96" align="right"/>

# Ridder HortiMaX Pro (HortOS) for Home Assistant

A Home Assistant custom integration for Ridder greenhouse controllers (HortiMaX Pro / MultiMa, CX500, ...) using the **Ridder HortOS Automation API**.

It is **read-only**: every readout that your controller publishes (climate, irrigation, weather station, ventilation, screens, ...) becomes a sensor in Home Assistant. Setpoints are never written.

## What you get

- One Home Assistant **device per greenhouse controller**, with a *connectivity* binary sensor showing its online status in the HortOS cloud.
- One Home Assistant **device per HortOS source** (e.g. *Weather station 001*, *Ventilation group 3*), linked to its controller.
- One **sensor per readout**, with units and device classes mapped to Home Assistant equivalents (temperature, humidity, CO₂, irradiance, wind speed, ...). Each sensor exposes the measurement timestamp, readout identifier, and source groups as attributes.
- New readouts that appear later are picked up automatically.

## Requirements

- A HortOS **API key**, requested from your Ridder account manager.
- Either the HortOS cloud API (default, `https://hortos.ridder.com/api/process-control`) or the on-premise API variant running on your local network.

## Installation

### HACS (recommended)

1. HACS → Integrations → ⋮ → *Custom repositories*.
2. Add this repository URL with category *Integration*.
3. Install **Ridder HortiMaX Pro (HortOS)** and restart Home Assistant.

### Manual

Copy `custom_components/hortimax` into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

Settings → Devices & Services → *Add integration* → **Ridder HortiMaX Pro (HortOS)**. Enter your API key (and adjust the base URL if you use the on-premise API).

The polling interval (default 60 s) can be changed under the integration's *Configure* option. Note that the controller publishes unchanged values at most every 5 minutes, and the API allows at most 100 requests per 15 seconds per API key; the integration uses one request per poll plus one per controller.

## Authentication details

The integration authenticates with your API key at `/v1/auth/apikey`, receiving a bearer token (valid 15 minutes) and a refresh token (valid 7 days). Tokens are refreshed automatically; if the API key is revoked, Home Assistant starts a re-authentication flow.

The HortOS API is documented with Swagger UI at <https://hortos.ridder.com/api/process-control/index.html>.

## Disclaimer

This is an unofficial integration and is not affiliated with Ridder. Use at your own risk.
