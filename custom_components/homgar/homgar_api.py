import hashlib
import logging
from datetime import datetime, timedelta, timezone

import aiohttp

from .const import (
    CONF_AREA_CODE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
)

_LOGGER = logging.getLogger(__name__)


class HomGarApiError(Exception):
    pass


class HomGarClient:
    def __init__(self, area_code: str, email: str, password: str, session: aiohttp.ClientSession):
        self._area_code = area_code
        self._email = email
        self._password = password  # cleartext, HA will store
        self._session = session

        self._token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: datetime | None = None

        self._base_url = "https://region3.homgarus.com"

    # --- token state helpers ---

    def restore_tokens(self, data: dict) -> None:
        """Restore tokens from config entry data."""
        self._token = data.get(CONF_TOKEN)
        self._refresh_token = data.get(CONF_REFRESH_TOKEN)
        ts = data.get(CONF_TOKEN_EXPIRES_AT)
        if ts is not None:
            self._token_expires_at = datetime.fromtimestamp(ts, tz=timezone.utc)

    def export_tokens(self) -> dict:
        """Export current token state as a dict for config entry updates."""
        return {
            CONF_TOKEN: self._token,
            CONF_REFRESH_TOKEN: self._refresh_token,
            CONF_TOKEN_EXPIRES_AT: int(self._token_expires_at.timestamp()) if self._token_expires_at else None,
        }

    def _token_valid(self) -> bool:
        if not self._token or not self._token_expires_at:
            return False
        # refresh a little before expiry
        return datetime.now(timezone.utc) < (self._token_expires_at - timedelta(minutes=5))

    # --- login / auth ---

    async def ensure_logged_in(self) -> None:
        if self._token_valid():
            return
        await self._login()

    async def _login(self) -> None:
        """Login with areaCode/email/password and store token info."""
        url = f"{self._base_url}/auth/basic/app/login"

        # Client-side MD5 hashing as per app/Postman flow
        md5 = hashlib.md5(self._password.encode("utf-8")).hexdigest()

        # Device ID is required; generate random 16 bytes hex
        device_id = hashlib.md5(f"{self._email}{self._area_code}".encode("utf-8")).hexdigest()

        payload = {
            "areaCode": self._area_code,
            "phoneOrEmail": self._email,
            "password": md5,
            "deviceId": device_id,
        }

        _LOGGER.debug("HomGar login request for %s", self._email)

        async with self._session.post(url, json=payload, headers={"Content-Type": "application/json", "lang": "en", "appCode": "1"}) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"Login HTTP {resp.status}")
            data = await resp.json()

        if data.get("code") != 0 or "data" not in data:
            raise HomGarApiError(f"Login failed: {data}")

        d = data["data"]
        self._token = d["token"]
        self._refresh_token = d.get("refreshToken")
        token_expired_secs = d.get("tokenExpired", 0)
        ts_server = data.get("ts")  # ms since epoch
        if ts_server:
            base = datetime.fromtimestamp(ts_server / 1000, tz=timezone.utc)
        else:
            base = datetime.now(timezone.utc)
        self._token_expires_at = base + timedelta(seconds=token_expired_secs)

        _LOGGER.info("HomGar login successful; token expires in %s seconds", token_expired_secs)

    def _auth_headers(self) -> dict:
        if not self._token:
            raise HomGarApiError("Token not available")
        return {"auth": self._token, "lang": "en", "appCode": "1"}

    # --- API calls ---

    async def list_homes(self) -> list[dict]:
        await self.ensure_logged_in()
        url = f"{self._base_url}/app/member/appHome/list"
        _LOGGER.debug("API call: list_homes URL=%s", url)
        async with self._session.get(url, headers=self._auth_headers()) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"list_homes HTTP {resp.status}")
            data = await resp.json()
        _LOGGER.debug("API response: list_homes data=%s", data)
        if data.get("code") != 0:
            raise HomGarApiError(f"list_homes failed: {data}")
        return data.get("data", [])

    async def get_devices_by_hid(self, hid: int) -> list[dict]:
        await self.ensure_logged_in()
        url = f"{self._base_url}/app/device/getDeviceByHid"
        params = {"hid": hid}
        _LOGGER.debug("API call: get_devices_by_hid URL=%s params=%s", url, params)
        async with self._session.get(url, params=params, headers=self._auth_headers()) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"getDeviceByHid HTTP {resp.status}")
            data = await resp.json()
        _LOGGER.debug("API response: get_devices_by_hid data=%s", data)
        if data.get("code") != 0:
            raise HomGarApiError(f"getDeviceByHid failed: {data}")
        return data.get("data", [])

    async def get_device_status(self, mid: int) -> dict:
        await self.ensure_logged_in()
        url = f"{self._base_url}/app/device/getDeviceStatus"
        params = {"mid": mid}
        _LOGGER.debug("API call: get_device_status URL=%s params=%s", url, params)
        async with self._session.get(url, params=params, headers=self._auth_headers()) as resp:
            if resp.status != 200:
                raise HomGarApiError(f"getDeviceStatus HTTP {resp.status}")
            data = await resp.json()
        _LOGGER.debug("API response: get_device_status data=%s", data)
        if data.get("code") != 0:
            raise HomGarApiError(f"getDeviceStatus failed: {data}")
        return data.get("data", {})


# --- Payload decoding helpers ---

def _parse_homgar_payload(raw: str) -> list[int]:
    """Turn '10#E1...' into [0-255] bytes list."""
    if not raw or not raw.startswith("10#"):
        raise ValueError(f"Unexpected payload format: {raw!r}")
    hex_str = raw[3:]
    if len(hex_str) % 2 != 0:
        raise ValueError(f"Hex payload length must be even: {hex_str}")
    out: list[int] = []
    for i in range(0, len(hex_str), 2):
        b = int(hex_str[i : i + 2], 16)
        out.append(b)
    return out


def _le16(bytes_: list[int], index: int) -> int:
    return bytes_[index] | (bytes_[index + 1] << 8)


def _f10_to_c(raw_f10: int) -> float:
    f = raw_f10 / 10.0
    return (f - 32.0) / 1.8


def _le_val(parts) -> int:
    """Interpret a list of bytes as a little-endian integer (LSB first)."""
    return int(''.join(f'{x:02x}' for x in reversed(parts)), 16)


def decode_moisture_simple(raw: str) -> dict:
    """
    Decode HCS026FRF (moisture-only) payload.
    Layout after '10#':
    b0 = 0xE1
    b1 = RSSI (signed int8)
    b2 = 0x00
    b3 = 0xDC
    b4 = 0x01
    b5 = 0x88  (moisture tag)
    b6 = moisture % (0-100)
    b7,b8 = status/battery field
    """
    b = _parse_homgar_payload(raw)
    if len(b) < 9:
        raise ValueError(f"Moisture simple payload too short: {b}")
    if b[5] != 0x88:
        raise ValueError(f"Expected 0x88 moisture tag at b[5], got {b[5]:02x}")
    rssi = b[1] - 256 if b[1] >= 128 else b[1]
    moisture = b[6]
    status_code = (b[7] << 8) | b[8]

    return {
        "type": "moisture_simple",
        "rssi_dbm": rssi,
        "moisture_percent": moisture,
        "battery_status_code": status_code,
        "raw_bytes": b,
    }


def decode_moisture_full(raw: str) -> dict:
    """
    Decode HCS021FRF (moisture + temp + lux).
    Layout after '10#':
    b0 = 0xE1
    b1 = RSSI (signed)
    b2 = 0x00
    b3 = 0xDC
    b4 = 0x01
    b5 = 0x85
    b6,b7 = temp_raw F*10 LE
    b8     = 0x88  (moisture tag)
    b9     = moisture %
    b10    = 0xC6  (lux tag)
    b11,b12= lux_raw * 10 LE
    b13    = 0x00
    b14,b15= 0xFF,0x0F (status/battery)
    """
    b = _parse_homgar_payload(raw)
    if len(b) < 16:
        raise ValueError(f"Moisture full payload too short: {b}")
    rssi = b[1] - 256 if b[1] >= 128 else b[1]

    temp_raw_f10 = _le16(b, 6)
    temp_c = _f10_to_c(temp_raw_f10)

    if b[8] != 0x88:
        raise ValueError(f"Expected 0x88 moisture tag at b[8], got {b[8]:02x}")
    moisture = b[9]

    if b[10] != 0xC6:
        raise ValueError(f"Expected 0xC6 lux tag at b[10], got {b[10]:02x}")
    lux_raw10 = _le16(b, 11)
    lux = lux_raw10 / 10.0

    status_code = (b[14] << 8) | b[15]

    return {
        "type": "moisture_full",
        "rssi_dbm": rssi,
        "moisture_percent": moisture,
        "temperature_c": temp_c,
        "temperature_f10": temp_raw_f10,
        "illuminance_lux": lux,
        "illuminance_raw10": lux_raw10,
        "battery_status_code": status_code,
        "raw_bytes": b,
    }


def decode_rain(raw: str) -> dict:
    """
    Decode HCS012ARF (rain gauge).
    Layout after '10#':
    b0 = 0xE1
    b1 = 0x00 (seems constant in your samples)
    b2 = 0x00
    b3,4 = FD,04 ; b5,b6 = lastHour raw*10 LE
    b7,8 = FD,05 ; b9,b10 = last24h raw*10 LE
    b11,12 = FD,06 ; b13,b14 = last7d raw*10 LE
    b15,16 = DC,01
    b17 = 0x97 ; b18,b19 = total raw*10 LE
    b20,b21 = 0x00,0x00
    b22,b23 = 0xFF,0x0F (status/battery)
    b24..b27 = tail
    """
    b = _parse_homgar_payload(raw)
    if len(b) < 24:
        raise ValueError(f"Rain payload too short: {b}")

    if not (b[3] == 0xFD and b[4] == 0x04):
        raise ValueError("Rain payload missing FD 04 at [3:5]")
    if not (b[7] == 0xFD and b[8] == 0x05):
        raise ValueError("Rain payload missing FD 05 at [7:9]")
    if not (b[11] == 0xFD and b[12] == 0x06):
        raise ValueError("Rain payload missing FD 06 at [11:13]")
    if b[17] != 0x97:
        raise ValueError(f"Rain payload missing 0x97 at b[17], got {b[17]:02x}")

    last_hour_raw10 = _le16(b, 5)
    last_24h_raw10 = _le16(b, 9)
    last_7d_raw10 = _le16(b, 13)
    total_raw10 = _le16(b, 18)

    status_code = (b[22] << 8) | b[23]

    return {
        "type": "rain",
        "rain_last_hour_mm": last_hour_raw10 / 10.0,
        "rain_last_24h_mm": last_24h_raw10 / 10.0,
        "rain_last_7d_mm": last_7d_raw10 / 10.0,
        "rain_total_mm": total_raw10 / 10.0,
        "rain_last_hour_raw10": last_hour_raw10,
        "rain_last_24h_raw10": last_24h_raw10,
        "rain_last_7d_raw10": last_7d_raw10,
        "rain_total_raw10": total_raw10,
        "battery_status_code": status_code,
        "raw_bytes": b,
    }


def decode_hws019wrf_v2(raw: str) -> dict:
    """
    Decode HWS019WRF-V2 (Display Hub) CSV/semicolon payload.
    Example: '1,0,1;788(788/777/1),68(68/64/1),P=9685(9684/9684/1),'
    """
    _LOGGER.debug("decode_hws019wrf_v2 called with raw: %r", raw)
    try:
        parts = raw.split(';')
        # First part: status flags (e.g., '1,0,1')
        flags = [int(x) for x in parts[0].split(',') if x.strip().isdigit()]
        readings = {}
        if len(parts) > 1:
            for item in parts[1].split(','):
                item = item.strip()
                if not item:
                    continue
                if '(' in item:
                    key, val = item.split('(', 1)
                    readings[key.strip()] = val.strip(')')
                elif '=' in item:
                    key, val = item.split('=', 1)
                    readings[key.strip()] = val.strip()
        result = {
            "type": "hws019wrf_v2",
            "flags": flags,
            "readings": readings,
            "raw": raw,
        }
        _LOGGER.debug("decode_hws019wrf_v2 result: %r", result)
        return result
    except Exception as ex:
        _LOGGER.warning("Failed to decode HWS019WRF-V2 payload: %s (raw: %r)", ex, raw)
        return {"type": "hws019wrf_v2", "raw": raw, "error": str(ex)}


def decode_temphum(raw: str) -> dict:
    """
    Decode HCS014ARF (temperature/humidity) payload.

    All byte indices are 0-based after stripping the '10#' prefix.
    Derived from Node-RED decoder: char position c → byte index (c - 3) / 2.

      b[1-2]   : templow    (2-byte LE, F*10 → °C)
      b[3-4]   : temphigh   (2-byte LE, F*10 → °C)
      b[10-11] : tempcurrent (2-byte LE, F*10 → °C)
      b[13]    : humiditycurrent (%)
      b[15]    : humiditylow (%)
      b[16]    : humidityhigh (%)
      b[17-18] : battery (2-byte LE, /4095*100 → %)
    """
    b = _parse_homgar_payload(raw)

    templow = ((_le_val(b[1:3]) / 10) - 32) * (5 / 9) if len(b) >= 3 else None
    temphigh = ((_le_val(b[3:5]) / 10) - 32) * (5 / 9) if len(b) >= 5 else None
    tempcurrent = ((_le_val(b[10:12]) / 10) - 32) * (5 / 9) if len(b) >= 12 else None
    humiditycurrent = b[13] if len(b) > 13 else None
    humiditylow = b[15] if len(b) > 15 else None
    humidityhigh = b[16] if len(b) > 16 else None
    tempbatt = _le_val(b[17:19]) / 4095 * 100 if len(b) >= 19 else None

    return {
        "type": "temphum",
        "templow": round(templow, 2) if templow is not None else None,
        "temphigh": round(temphigh, 2) if temphigh is not None else None,
        "tempcurrent": round(tempcurrent, 2) if tempcurrent is not None else None,
        "humiditycurrent": humiditycurrent,
        "humidityhigh": humidityhigh,
        "humiditylow": humiditylow,
        "tempbatt": round(tempbatt, 2) if tempbatt is not None else None,
        "raw_bytes": b,
    }


def decode_flowmeter(raw: str) -> dict:
    """
    Decode HCS008FRF (flowmeter) payload.

    Packet layout (byte indices, 0-based, after stripping '10#' prefix):
      b[0]       : 0xE1 marker
      b[1]       : RSSI / counter
      b[2]       : 0x00
      b[3-4]     : FF 0B marker+tag
      b[5-8]     : zeros
      b[9-13]    : DC 01 99 00 00  (counters/version)
      b[14-18]   : 5-byte timestamp 1
      b[19]      : 0xFF marker
      b[20]      : 0x07 tag (current flow)
      b[21-23]   : flowcurrentused  (3-byte LE, /10 → litres)
      b[24]      : 0x00
      b[25]      : 0xAF tag (current duration)
      b[26-28]   : flowcurrenduration  (3-byte LE, seconds)
      b[29]      : 0x00
      b[30]      : 0x9F tag (last used)
      b[31-33]   : flowlastused  (3-byte LE, /10 → litres)
      b[34]      : 0x00
      b[35]      : 0xFF marker
      b[36]      : 0x0A tag (last duration)
      b[37-39]   : flowlastusedduration  (3-byte LE, seconds)
      b[40]      : 0x00
      b[41]      : 0xCB tag (total today)
      b[42-44]   : flowtotaltoday  (3-byte LE, /10 → litres)
      b[45]      : 0x00
      b[46]      : 0xB3 tag (total)
      b[47-50]   : flowtotal  (4-byte LE, /10 → litres)
      b[51]      : 0xFF marker
      b[52-53]   : battery  (2-byte BE, /4095*100 → %)
      b[54-56]   : 3-byte timestamp 2 tail
    """
    b = _parse_homgar_payload(raw)

    flowcurrentused = _le_val(b[21:24]) / 10 if len(b) >= 24 else None
    flowcurrenduration = _le_val(b[26:29]) if len(b) >= 29 else None
    flowlastused = _le_val(b[31:34]) / 10 if len(b) >= 34 else None
    flowlastusedduration = _le_val(b[37:40]) if len(b) >= 40 else None
    flowtotaltoday = _le_val(b[42:45]) / 10 if len(b) >= 45 else None
    flowtotal = _le_val(b[47:51]) / 10 if len(b) >= 51 else None
    # Battery is stored big-endian (MSB at lower address)
    flowbatt = ((b[52] << 8) | b[53]) / 4095 * 100 if len(b) >= 54 else None

    return {
        "type": "flowmeter",
        "flowcurrentused": flowcurrentused,
        "flowcurrenduration": flowcurrenduration,
        "flowlastused": flowlastused,
        "flowlastusedduration": flowlastusedduration,
        "flowtotaltoday": flowtotaltoday,
        "flowtotal": flowtotal,
        "flowbatt": round(flowbatt, 1) if flowbatt is not None else None,
        "raw_bytes": b,
    }


def decode_co2(raw: str) -> dict:
    """
    Decode HCS0530THO (CO2/temp/humidity) payload.

    All byte indices are 0-based after stripping the '10#' prefix.
    Derived from Node-RED decoder: char position c → byte index (c - 3) / 2.

      b[1-2]   : CO2 current (2-byte LE, ppm)
      b[15-16] : co2temp (2-byte LE, F*10 → °C)
      b[18]    : co2humidity (%)
      b[24-25] : co2low (2-byte LE, ppm)
      b[26-27] : co2high (2-byte LE, ppm)
      b[28-29] : battery (2-byte LE, /4095*100 → %)
      b[32]    : RSSI (subtract 256 for signed dBm)
    """
    b = _parse_homgar_payload(raw)

    co2 = _le_val(b[1:3]) if len(b) >= 3 else None
    co2low = _le_val(b[24:26]) if len(b) >= 26 else None
    co2high = _le_val(b[26:28]) if len(b) >= 28 else None
    co2temp = (((_le_val(b[15:17]) / 10) - 32) * (5 / 9)) if len(b) >= 17 else None
    co2humidity = b[18] if len(b) > 18 else None
    co2batt = _le_val(b[28:30]) / 4095 * 100 if len(b) >= 30 else None
    co2rssi = b[32] - 256 if len(b) > 32 else None

    return {
        "type": "co2",
        "co2": co2,
        "co2low": co2low,
        "co2high": co2high,
        "co2temp": round(co2temp, 2) if co2temp is not None else None,
        "co2humidity": co2humidity,
        "co2batt": round(co2batt, 2) if co2batt is not None else None,
        "co2rssi": co2rssi,
        "raw_bytes": b,
    }


def decode_pool(raw: str) -> dict:
    """
    Decode HCS0528ARF (pool/temperature) payload.

    All byte indices are 0-based after stripping the '10#' prefix.
    Derived from Node-RED decoder: char position c → byte index (c - 3) / 2.

      b[1-2]   : templow    (2-byte LE, F*10 → °C)
      b[3-4]   : temphigh   (2-byte LE, F*10 → °C)
      b[10-11] : tempcurrent (2-byte LE, F*10 → °C)
      b[13], b[11] : battery (non-sequential per Node-RED, /4095*100 → %)
    """
    b = _parse_homgar_payload(raw)

    templow = ((_le_val(b[1:3]) / 10) - 32) * (5 / 9) if len(b) >= 3 else None
    temphigh = ((_le_val(b[3:5]) / 10) - 32) * (5 / 9) if len(b) >= 5 else None
    tempcurrent = ((_le_val(b[10:12]) / 10) - 32) * (5 / 9) if len(b) >= 12 else None
    # Battery uses non-sequential bytes b[13] (high) and b[11] (low) per Node-RED reference
    tempbatt = ((b[13] << 8) | b[11]) / 4095 * 100 if len(b) >= 14 else None

    return {
        "type": "pool",
        "templow": round(templow, 2) if templow is not None else None,
        "temphigh": round(temphigh, 2) if temphigh is not None else None,
        "tempcurrent": round(tempcurrent, 2) if tempcurrent is not None else None,
        "tempbatt": round(tempbatt, 2) if tempbatt is not None else None,
        "raw_bytes": b,
    }
