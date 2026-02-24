# HomGar Cloud integration for Home Assistant

Unofficial Home Assistant component for HomGar Cloud, supporting RF soil moisture, rain, flow meter, temperature/humidity, CO2, and pool temperature sensors via the HomGar cloud API.

This is a personal fork of [brettmeyerowitz/homeassistant-homgar](https://github.com/brettmeyerowitz/homeassistant-homgar), tweaked to work with my own setup. Though you're welcome to use this fork as-is, it is not actively maintained — if you're looking for a general-purpose integration, the original repository is a better starting point.

---

## Compatibility

Personally tested with:
- Hub: `HWG023WBRF-V2`
- Rain gauge: `HCS012ARF`
- Flowmeter: `HCS008FRF`

The following are supported in code (ported from the original) but not personally tested:
- Soil moisture probes: `HCS026FRF`, `HCS021FRF`
- Temperature/Humidity: `HCS014ARF`
- CO2/Temperature/Humidity: `HCS0530THO`
- Pool/Temperature: `HCS0528ARF`

The integration communicates with the same cloud endpoints as the HomGar app (`region3.homgarus.com`).

---

## Features

- Login with your HomGar account (email + area code)
- Select which homes to include
- Auto-discovers supported sub-devices
- Exposes:
  - Moisture %
  - Temperature (where applicable)
  - Illuminance (HCS021FRF)
  - Rain:
    - Last hour
    - Last 24 hours
    - Last 7 days
    - Total rainfall (`TOTAL_INCREASING` for Utility Meter / statistics)
  - Temperature/Humidity (HCS014ARF): current, high, low + humidity
  - Flowmeter (HCS008FRF): current session, last session, total today, all-time total (`TOTAL_INCREASING`), battery
  - CO2, temperature, humidity, battery (HCS0530THO)
  - Pool temperature: current, high, low, battery (HCS0528ARF)
- Attributes per sensor:
  - `rssi_dbm`
  - `battery_status_code`
  - `last_updated` (cloud timestamp)

---

## Installation

### Easy Installation via HACS

You can quickly add this repository to HACS by clicking the button below:

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=fredi-e&repository=homeassistant-homgar&category=integration)

Or add it manually in HACS: **HACS → Integrations → ⋮ → Custom repositories** and add `https://github.com/fredi-e/homeassistant-homgar` as an Integration.

### Manual Installation

1. Copy the `custom_components/homgar` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

---

## Configuration

Go to **Settings → Devices & Services → Add Integration** and search for **HomGar Cloud**. Enter your HomGar account credentials (email and area code) to connect.

---

## Tracking daily/monthly usage (Utility Meter)

The `Flow Total` and `Rain Total` sensors use `state_class: total_increasing`, making them compatible with Home Assistant's [Utility Meter](https://www.home-assistant.io/integrations/utility_meter/) integration for calendar-based daily and monthly tracking.

Example `configuration.yaml`:

```yaml
utility_meter:
  flow_daily:
    source: sensor.borehole_flow_flow_total
    cycle: daily
  flow_monthly:
    source: sensor.borehole_flow_flow_total
    cycle: monthly
  rain_monthly:
    source: sensor.rain_meter_rain_total
    cycle: monthly
```

---

## Credits

Originally developed by [Brett Meyerowitz](https://github.com/brettmeyerowitz). Tweaked by [@fredi-e](https://github.com/fredi-e) for personal use.

**Special thanks to [shaundekok/rainpoint](https://github.com/shaundekok/rainpoint) for Node-RED flow inspiration, payload decoding, and entity mapping logic.**

Feedback and contributions are welcome via the [issue tracker](https://github.com/fredi-e/homeassistant-homgar/issues).
