#!/usr/bin/env python3
"""Print the current fan speed of a single Broadlink AC.

Two ways to point it at a device:

  1. Use the config in settings/config.yml and select by MAC (or index):
       .venv/bin/python get_fanspeed.py --config settings/config.yml <MAC>
       .venv/bin/python get_fanspeed.py --config settings/config.yml --index 0

  2. Point it directly at a device on the LAN (no config needed):
       .venv/bin/python get_fanspeed.py --ip 192.168.1.236 --mac 34ea34e74e55

The FAN enum in ac_db.py only maps LOW/MEDIUM/HIGH/AUTO/NONE (0,1,2,3,5). Some
ACs report values like 4/6/7 which are NOT in that enum; those show up here as
the raw integer too, alongside the bits that make up the reported state.
"""
import argparse
import os
import sys
import time

# Make the bundled broadlink package importable the same way monitor.py does.
sys.path.insert(1, os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                "broadlink_ac_mqtt", "classes", "broadlink"))
import broadlink_ac_mqtt.classes.broadlink.ac_db as broadlink  # noqa: E402


# Mirror of STATIC.FAN (ac_db.py) so we can show the raw value's meaning.
FAN_LABELS = {
    0b00000000: "NONE",
    0b00000001: "MEDIUM_HIGH",      # raw=1, app 75%
    0b00000010: "MEDIUM",           # raw=2, IR-remote only
    0b00000011: "LOW",              # raw=3, app 50% (+mute=25%)
    0b00000101: "HIGH",             # raw=5, app 100%
    0b00000110: "HIGH (alt)",       # raw=6, IR-remote only, between 75% and 100%
    0b00000111: "AUTO",             # raw=7, auto (cooling mode)
}
# Value 4 is reported by some models but is not in the enum.


def load_devices_from_config(config_path):
    import yaml
    with open(config_path, "r") as f:
        cfg = yaml.load(f, Loader=yaml.SafeLoader)
    return cfg.get("devices") or []


def pick_device_from_config(config_path, mac=None, index=None):
    devices = load_devices_from_config(config_path)
    if not devices:
        sys.exit("No 'devices:' entries found in %s" % config_path)

    if mac:
        mac_norm = mac.lower().replace("-", "").replace(":", "")
        for d in devices:
            if d["mac"].lower() == mac_norm:
                return d
        sys.exit("Device with mac %s not found in %s. Known: %s"
                 % (mac, config_path, ", ".join(d["mac"] for d in devices)))

    if index is not None:
        if index < 0 or index >= len(devices):
            sys.exit("Index %d out of range (0..%d)" % (index, len(devices) - 1))
        return devices[index]

    # No selector: list what's available and exit.
    print("Multiple devices in config. Pick one with --mac <MAC> or --index <N>:\n")
    for i, d in enumerate(devices):
        print("  [%d] %s  %-18s  %s:%s" % (i, d["mac"], d.get("name", ""), d["ip"], d.get("port", 80)))
    sys.exit(0)


def build_device(ip, port, mac_hex, name=None):
    mac = bytearray.fromhex(mac_hex)
    return broadlink.gendevice(devtype=0x4E2a, host=(ip, port), mac=mac,
                               name=name, cloud=None, update_interval=0)


def main():
    p = argparse.ArgumentParser(
        description="Read the current fan speed of a single Broadlink AC.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    src = p.add_argument_group("device source (use one of these)")
    src.add_argument("-c", "--config", help="Path to config.yml (select a device from it)")
    src.add_argument("--index", type=int, help="Index into config 'devices' list (0-based)")
    src.add_argument("--mac", help="MAC of the device to select from config (e.g. 34ea34e74e55)")
    src.add_argument("--ip", help="Talk directly to this IP (no config needed)")
    src.add_argument("--port", type=int, default=80, help="AC port (default 80, only with --ip)")
    args = p.parse_args()

    if args.config:
        d = pick_device_from_config(args.config, mac=args.mac, index=args.index)
        ip, port, mac_hex, name = d["ip"], d.get("port", 80), d["mac"], d.get("name")
    elif args.ip:
        if not args.mac:
            sys.exit("--ip also requires --mac (e.g. --mac 34ea34e74e55)")
        ip, port, mac_hex, name = args.ip, args.port, args.mac, None
    else:
        # Default: look for settings/config.yml next to this script.
        default_cfg = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                   "settings", "config.yml")
        if os.path.exists(default_cfg):
            d = pick_device_from_config(default_cfg, mac=args.mac, index=args.index)
            ip, port, mac_hex, name = d["ip"], d.get("port", 80), d["mac"], d.get("name")
        else:
            p.error("no device source: pass --config or --ip/--mac, "
                    "or place settings/config.yml next to this script")

    # Silence the library's INFO logging; we want a clean single-line answer.
    import logging
    logging.basicConfig(level=logging.CRITICAL)

    print("Connecting to %s (%s:%d, name=%r) ..." % (mac_hex, ip, port, name),
          file=sys.stderr)
    dev = build_device(ip, port, mac_hex, name)
    if dev is False:
        sys.exit("ERROR: authentication/initialisation failed (is the AC online?)")

    # __init__ already forces a status fetch; refresh once more to be safe.
    status = dev.get_ac_status(force_update=True)
    if not status:
        sys.exit("ERROR: could not read AC status (no response from device)")

    raw = dev.status["fanspeed"]
    label = FAN_LABELS.get(raw, "<unmapped>")
    ha = status.get("fanspeed_homeassistant", "?")

    print("")
    print("device        : %s  (%s)" % (mac_hex, name or "(no name)"))
    print("power         : %s" % status.get("power"))
    print("mode          : %s" % status.get("mode"))
    print("temp (set)    : %s" % status.get("temp"))
    print("ambient_temp  : %s" % status.get("ambient_temp"))
    print("mute          : %s" % status.get("mute"))
    print("turbo         : %s" % status.get("turbo"))
    print("-" * 40)
    print("fanspeed raw  : %d  (3-bit value 0..7)" % raw)
    print("fanspeed label: %s" % label)
    print("fanspeed HA   : %s" % ha)


if __name__ == "__main__":
    main()
