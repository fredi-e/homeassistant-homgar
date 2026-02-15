# HomGar Cloud integration for Home Assistant

Unofficial Home Assistant component for HomGar Cloud, supporting RF soil moisture and rain sensors via the HomGar cloud API.

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
    - Total rainfall
- Attributes:
  - `rssi_dbm`
  - `battery_status_code`
  - `last_updated` (cloud timestamp)

## Compatibility

Tested with:
- Hub: `HWG023WBRF-V2`
- Soil moisture probes:
  - `HCS026FRF` (moisture-only)
  - `HCS021FRF` (moisture + temperature + lux)
- Rain gauge:
  - `HCS012ARF`

The integration communicates with the same cloud endpoints as the HomGar app (`region3.homgarus.com`).

---

## Installation

### Easy Installation via HACS

You can quickly add this repository to HACS by clicking the button below:

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=brettmeyerowitz&repository=homeassistant-homgar&category=integration)

#### Manual Installation

1. Copy the `custom_components/homgar` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

---

## Configuration

Go to **Settings → Devices & Services → Add Integration** and search for **HomGar Cloud**. Enter your HomGar account credentials (email and area code) to connect.

---

## Example manifest.json

Below is the manifest file for this integration (as of version 0.1.1):

```json
{
    "domain": "homgar",
    "name": "HomGar Cloud",
    "version": "0.1.1",
    "documentation": "https://github.com/brettmeyerowitz/homeassistant-homgar",
    "issue_tracker": "https://github.com/brettmeyerowitz/homeassistant-homgar/issues",
    "requirements": [],
    "codeowners": [
        "@brettmeyerowitz"
    ],
    "config_flow": true,
    "iot_class": "cloud_polling",
    "integration_type": "hub",
    "loggers": [
        "custom_components.homgar"
    ]
}
```

---

## Credits

This integration was developed by Brett Meyerowitz. It is not affiliated with HomGar. Feedback and contributions are welcome!
