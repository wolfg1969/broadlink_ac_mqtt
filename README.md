# Broadlink Air Conditioners to MQTT

> **Note about this fork**
>
> This repository is a fork of `liaan/broadlink_ac_mqtt`, which has since been archived. The fork keeps the bridge working on modern Python, hardens the MQTT/polling loop, adds Docker support, and includes a small diagnostic tool. See [CLAUDE.md](CLAUDE.md) for design notes and a full list of changes.
>
> Recent improvements in this fork:
> - Removed `pycrypto`; uses `cryptography` for AES.
> - Reuses a single MQTT client with paho auto-reconnect and a per-poll LWT heartbeat, so Home Assistant no longer gets stuck on `unavailable`.
> - Polls only devices that are due instead of busy-waiting in 0.5 s slices.
> - Expanded fan-speed mapping (`Medium_High`, `High` alt, `Auto`) with normalisation for Home Assistant.
> - Added `get_fanspeed.py` to inspect a single AC's fan speed.
> - Added `Dockerfile` and `docker-compose.yml`.
> - Logging verbosity can be set with the `LOGLEVEL` environment variable.

---

# ALERT:!!!   Archived (upstream)

There are simply too many new aircons that don't work with this code anymore, and enough other forks to keep older AC's going.

Also, my AC's are working fine.. so no motivation to keep this up to date.

------------------------------------------------------------------------------

## Telegram Group

https://t.me/+1Xw9Kwr2P7k2YjY0

## Donations

[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](http://www.paypal.me/liaanvdm)

#### BTC Donations: 1DaGtHqaYvvDrXcpiNoNkNJgkmm6dEp7Lq
----------------------------------------------------------------------------------------------------------------

## Docker version

A `Dockerfile` and `docker-compose.yml` are included in this fork. See the Docker section below.

The separate Docker repository is still available at https://github.com/broadlink-ac/broadlink_ac_mqtt_docker.

#### Air Conditioners compatibility
  * Dunham bush --> Tested and working
  * Rcool Solo --> Tested and working
  * Akai 9000BTU  --> Tested and working
  * Rinnai  --> Tested and working .. autodiscovery name seems to be buggy
  * Kenwood --> In Testing
  * Tornado X (2019 and up) --> Tested and working
    * Tornado top wifi 12x a.c Tested and reported as working
  * AUX ASW-H09A4/DE-R1DI (Broadlink module) --> Tested and working
  * Ballu BSUI/IN-12HN8 (with integrated Wi-Fi module and AC Freedom app). --> Tested and working
  * In theory any Broadlink devtype == 0x4E2a (20010) using the AC Freedom APP

## Installation

### Using a virtual environment (recommended)

Requires Python 3.10 (the pinned dependencies only ship prebuilt wheels up to 3.10):

```
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run with the venv interpreter (no activation needed):

```
.venv/bin/python monitor.py
```

### Using Docker

```
cp settings/sample_config.yml settings/config.yml
# edit settings/config.yml with your MQTT broker and devices
docker compose up -d --build
```

Host networking (`network_mode: host`) is required because device discovery sends UDP broadcasts to `255.255.255.255:80`. The container's default data directory is `/app`, so `settings/config.yml` and `log/out.log` are mounted from the host.

### Global install

```
pip install -r requirements.txt
```

### Configuration

1. Copy `settings/sample_config.yml` to `settings/config.yml` (or the data-dir you specified).
2. Edit the config to match your environment.
3. Run `./monitor.py` (or `python monitor.py`, or `.venv/bin/python monitor.py`).

If you are lazy and just want to copy and paste your devices, use the `-S` option and discovered devices config will be printed to screen for copy/paste.

Example:
```
root@berry1:~/ac_db# ./monitor.py -S
*********** start copy below ************
devices:
- ip: 10.0.0.227
  mac: b4430da741af
  name: Office
  port: 80

*********** stop copy above ************
```

**Note:**
Some devices (confirmed on AUX conditioner) return device **name** in Chinese, like '奥克斯空调'.
Device renaming in 'AC Freedom' app does not affect it. You can see empty **name** in `-S` option output or any artifacts.
So in case `-S` returns empty value and you plan to use HASS autodiscovery - the best way is to configure your device manually in `config.yml` and set `self_discovery: False`.

### Logging

By default the bridge logs to `log/out.log`. Verbosity defaults to `INFO` and can be changed with the `LOGLEVEL` environment variable (`DEBUG`, `INFO`, `WARNING`, `ERROR`). The `-d` / `--debug` flag still forces DEBUG.

```
LOGLEVEL=DEBUG .venv/bin/python monitor.py
```

## Command line arguments

```
optional arguments:
  -h, --help            show this help message and exit
  -Hd, --dumphaconfig   Dump the devices as a HA manual config entry
  -Hat MQTT_AUTO_DISCOVERY_TOPIC, --mqtt_auto_discovery_topic MQTT_AUTO_DISCOVERY_TOPIC
                        If specified, will Send the MQTT autodiscovery config
                        for all devices to topic
  -b, --background      Run in background
  -S, --discoverdump    Discover devices and dump config
  -ms MQTTSERVER, --mqttserver MQTTSERVER
                        Mqtt Server, Default:
  -mp MQTTPORT, --mqttport MQTTPORT
                        Mqtt Port
  -mU MQTTUSER, --mqttuser MQTTUSER
                        Mqtt User
  -mP MQTTPASSWORD, --mqttpassword MQTTUSER
                        Mqtt Password
  -s, --discover        Discover devices
  -d, --debug           Set logging level to debug
  -v, --version         Print Versions
  -dir DATA_DIR, --data_dir DATA_DIR
                        Data Folder -- Default to folder script is located
  -c CONFIG, --config CONFIG
                        Config file path -- Default to folder script is located + 'config.yml'
```

Examples:

Run in background:
```
./monitor.py -b
```

Run with full debugging:
```
./monitor.py -d
```

Dump all discovered devices so one can copy paste:
```
./monitor.py -S
```

## MQTT topics

To set values, publish to `/aircon/<mac_address>/<option>/value/set`:

```
/aircon/b4430dce73f1/temp/set 20
```

Availability is published (retained) on `/aircon/LWT` (`online` / `offline`).

## Diagnostic tools

### Read a single AC's fan speed

`get_fanspeed.py` connects to one AC and prints the raw 3-bit fan value, the mapped label, and the Home Assistant fan mode.

From config:
```
.venv/bin/python get_fanspeed.py --config settings/config.yml <MAC>
.venv/bin/python get_fanspeed.py --config settings/config.yml --index 0
```

Directly by IP/MAC (no config needed):
```
.venv/bin/python get_fanspeed.py --ip 192.168.1.236 --mac 34ea34e74e55
```

## Home Assistant (www.home-assistant.io) Options

### MQTT autodiscovery

MQTT autodiscovery works for Home Assistant (https://www.home-assistant.io/docs/mqtt/discovery/).

Edit `config.yml` and add below if not there. If already there, make sure the prefix matches `configuration.yaml` in HA:

```
mqtt:
  discovery: true
  auto_discovery_topic: homeassistant
```

**To add a device manually using the configuration.yaml in HA you can create an easy config to copy/paste by using `-Hd` (`--dumphaconfig`). Just make sure your `config.yml` is updated with correct settings before running.**

This is also nice to verify the autoconfig that gets sent to HA using MQTT autoconfig.

Example:

```
root@berry1:~/ac_db# ./monitor.py -Hd

*********** start copy below ****************
climate:
- action_topic: /aircon/b4430dce73f1/homeassistant/set
  current_temperature_topic: /aircon/b4430dce73f1/ambient_temp/value
  fan_mode_command_topic: /aircon/b4430dce73f1/fanspeed_homeassistant/set
  fan_mode_state_topic: /aircon/b4430dce73f1/fanspeed_homeassistant/value
  fan_modes:
  - Auto
  - Low
  - Medium
  - Medium_High
  - High
  - Turbo
  - Mute
  max_temp: 32.0
  min_temp: 16.0
  mode_command_topic: /aircon/b4430dce73f1/mode_homeassistant/set
  mode_state_topic: /aircon/b4430dce73f1/mode_homeassistant/value
  modes:
  - 'off'
  - cool
  - heat
  - fan_only
  - dry
  name: Living Room
  platform: mqtt
  precision: 0.5
  temperature_command_topic: /aircon/b4430dce73f1/temp/set
  temperature_state_topic: /aircon/b4430dce73f1/temp/value

*********** stop copy above ************
```
