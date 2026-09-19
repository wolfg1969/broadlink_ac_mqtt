# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This is a fork of `liaan/broadlink_ac_mqtt`, a Python bridge that controls Broadlink-based air conditioners (device type `0x4E2a`, commonly used by the AC Freedom app) over UDP and exposes them through MQTT. It can be used standalone or as an MQTT discovery source for Home Assistant.

The upstream repository is archived. This fork keeps the code working on modern Python, adds container support, hardens the MQTT/polling loop, and provides a small diagnostic tool for fan-speed mapping.

## Repository layout

```
monitor.py                          # CLI entry point: parses args/config, starts the bridge
broadlink_ac_mqtt/AcToMqtt.py       # MQTT client, polling loop, HA auto-discovery, command dispatch
broadlink_ac_mqtt/classes/broadlink/ac_db.py  # UDP protocol implementation for the AC
get_fanspeed.py                     # Diagnostic: read one AC's fan speed from config or IP/MAC
settings/sample_config.yml          # Example configuration
Dockerfile / docker-compose.yml     # Container packaging
```

## Running and developing

### Virtual environment (recommended)

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the bridge:

```bash
.venv/bin/python monitor.py
```

Force debug logging:

```bash
.venv/bin/python monitor.py -d
```

Or tune verbosity without editing code via the `LOGLEVEL` environment variable (default `INFO`):

```bash
LOGLEVEL=DEBUG .venv/bin/python monitor.py
```

### Docker

```bash
cp settings/sample_config.yml settings/config.yml
# edit settings/config.yml with your MQTT broker and devices
docker compose up -d --build
```

Host networking (`network_mode: host`) is required because device discovery broadcasts UDP to `255.255.255.255:80`.

### Diagnostic tools

Discover devices and dump a config snippet:

```bash
.venv/bin/python monitor.py -S
```

Dump Home Assistant manual climate config for verification:

```bash
.venv/bin/python monitor.py -Hd
```

Read a single AC's current fan speed:

```bash
.venv/bin/python get_fanspeed.py --config settings/config.yml <MAC>
.venv/bin/python get_fanspeed.py --ip 192.168.1.236 --mac 34ea34e74e55
```

### Lint / format

There is no test suite or formal linter config. The last commit ran `autopep8` over the Python files. When editing, prefer to keep surrounding style rather than reformatting entire files.

## Architecture

### Protocol stack

1. **UDP device layer** — `broadlink_ac_mqtt/classes/broadlink/ac_db.py`
   - `device` handles Broadlink authentication, AES-CBC encryption, packet framing, checksums, and the UDP socket.
   - `ac_db` is the AC-specific subclass. It parses status packets (`get_ac_states`), builds command packets (`set_ac_status`), and exposes high-level helpers such as `set_temperature`, `set_fanspeed`, `switch_on/off`, etc.
   - Each setter first calls `get_ac_states()` because the AC requires the full state bitmap on every write.

2. **MQTT bridge layer** — `broadlink_ac_mqtt/AcToMqtt.py`
   - `AcToMqtt.connect_mqtt()` builds a single `paho.mqtt.client` instance with auto-reconnect enabled and a last-will testament on `<prefix>/LWT`.
   - `AcToMqtt.start()` is the main polling loop. It sleeps until the next device is due, polls only due devices, and publishes changed values.
   - `AcToMqtt.publish_mqtt_info()` skips unchanged values to keep MQTT traffic low, unless HA auto-discovery is enabled (then it forces updates).
   - `AcToMqtt._on_mqtt_message()` dispatches incoming `/aircon/<mac>/<function>/set` messages to the matching device object.

3. **CLI / bootstrap** — `monitor.py`
   - Loads `settings/config.yml` (or root `config.yml`), applies CLI overrides, discovers or instantiates devices, then calls `AcToMqtt.start()` in a loop when running as a daemon.

### Important implementation details

- **Polling interval**: controlled by `service.update_interval` in `config.yml`. The loop waits in one shot until the earliest due device; do not revert to busy-waiting.
- **MQTT availability**: the bridge publishes `online` (retained) to `<prefix>/LWT` on every poll cycle, not only at connect time. This prevents Home Assistant from staying `unavailable` after a transient disconnect that triggers the will `offline`.
- **MQTT client reuse**: `connect_mqtt()` creates the client once. Recreating it under the same `client_id` caused the broker to evict the previous connection and produced a reconnect storm.
- **Fan speed mapping**: the raw 3-bit fan value is mapped in `ac_db.STATIC.FAN`. This fork adds `MEDIUM_HIGH` (raw 1), `HIGH_ALT` (raw 6), and `AUTO` (raw 7); `HIGH_ALT` is normalised to `HIGH` for Home Assistant. `make_nice_status()` also overrides the fan label with `TURBO`/`MUTE` when those flags are on.
- **Config discovery fallback**: `monitor.py` looks for `settings/config.yml` first, then `config.yml` in the script directory, and exits with a clear message if neither exists.

### Topic conventions

- State topics: `/aircon/<mac>/<field>/value`
- Command topics: `/aircon/<mac>/<field>/set`
- Availability: `/aircon/LWT`
- HA auto-discovery: `<auto_discovery_topic>/climate/<mac>/config`

Command fields handled in `_on_mqtt_message()` include `temp`, `power`, `mode`, `fanspeed`, `fanspeed_homeassistant`, `mode_homeassistant`, `mode_homekit`, `fixation_v`, `fixation_h`, `display`, `mildew`, `clean`, `health`, `sleep`, and `state refresh`.

## Fork-specific changes

Compared to the archived upstream:

- Modern Python support: removed the `pycrypto` dependency and switched to `cryptography` for AES.
- Added venv setup instructions and `.venv/` to `.gitignore`.
- Fixed discovery/config bugs: empty device names now fall back to the MAC hex string, config paths use `os.path.join`, and missing `config.yml` produces a clear error.
- Hardened MQTT: single reused client, paho auto-reconnect, and a per-poll LWT heartbeat so HA does not get stuck unavailable.
- Hardened polling loop: sleep until the next due device and poll only due devices instead of every device every half second.
- Expanded fan-speed enum and normalised `HIGH_ALT` to `HIGH` for Home Assistant compatibility.
- Added `get_fanspeed.py` diagnostic tool.
- Added `Dockerfile`, `docker-compose.yml`, and `.dockerignore`; pinned to Python 3.10 because the locked dependencies only provide wheels up to that version.
- Logging level can be set with the `LOGLEVEL` environment variable; `-d` still forces DEBUG.
- Code formatted with `autopep8`.
