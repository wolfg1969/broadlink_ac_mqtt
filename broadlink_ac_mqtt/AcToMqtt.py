#!/usr/bin/python
import broadlink_ac_mqtt.classes.broadlink.ac_db as broadlink
import os
import time
import sys
import logging
import argparse
import yaml
import paho.mqtt.client as mqtt
import tempfile
import json
import traceback

sys.path.insert(1, os.path.join(os.path.dirname(
    os.path.realpath(__file__)), 'classes', 'broadlink'))


logger = logging.getLogger(__name__)

config = {}
device_objects = {}


class AcToMqtt:
    previous_status = {}
    last_update = {}

    def __init__(self, config):
        self.config = config
        self._mqtt = None
        # Per-device availability: consecutive poll failures, and the last
        # availability state published (True/False, absent means unknown).
        self._device_failures = {}
        self._device_available = {}
        ""

    def test(self, config):

        for device in config['devices']:

            device_bla = broadlink.gendevice(devtype=0xFFFFFFF, host=(
                device['ip'], device['port']), mac=bytearray.fromhex(device['mac']), name=device['name'])
            status = device_bla.set_temperature(32)
            # print status

    def discover(self):

        # Go discovery
        discovered_devices = broadlink.discover(
            timeout=5, bind_to_ip=self.config['bind_to_ip'])
        devices = {}

        if discovered_devices == None:
            error_msg = "No Devices Found, make sure you on the same network segment"
            logger.debug(error_msg)

            # print "nothing found"
            sys.exit()

        # Make sure correct device id
        for device in discovered_devices:
            if device.devtype == 0x4E2a:
                devices[device.status['macaddress']] = device

        return devices

    def make_device_objects(self, device_list=None):
        device_objects = {}

        if device_list == [] or device_list == None:
            error_msg = " Cannot make device objects, empty list given"
            logger.error(error_msg)
            sys.exit()

        for device in device_list:
            device_objects[device['mac']] = broadlink.gendevice(devtype=0x4E2a, host=(device['ip'], device['port']), mac=bytearray.fromhex(
                device['mac']), name=device['name'], update_interval=self.config['update_interval'])

        return device_objects

    def stop(self):

        try:
            self._mqtt.disconnect()
        except:
            ""

    def start(self, config, devices=None):

        self.device_objects = devices
        self.config = config

        # If there no devices so throw error
        if devices == [] or devices == None:
            print("No devices defined")
            logger.error(
                "No Devices defined, either enable discovery or add them to config")
            return
        else:
            logger.debug("Following devices configured %s" % repr(devices))

        # we are alive ##Update PID file
        try:
            # Refresh the LWT availability "online" marker on every cycle so a
            # transient disconnect's retained "offline" cannot leave HA stuck
            # on "unavailable" between reconnects.
            self._publish_online()

            interval = self.config["update_interval"]
            now = time.time()

            # Sleep in one shot until the earliest device is due, instead of
            # busy-waiting in 0.5s slices between polls. Devices that have not
            # been polled yet (e.g. on startup) are due immediately.
            if all(key in self.last_update for key in devices):
                next_due = min(
                    self.last_update[key] + interval for key in devices)
                if next_due > now:
                    time.sleep(next_due - now)

            # Poll only the devices that are actually due
            for key in devices:
                device = devices[key]
                if key in self.last_update and (self.last_update[key] + interval) > time.time():
                    continue

                # Record the attempt up front, so a failing device waits a full
                # interval before retrying instead of being retried non-stop by
                # the caller's loop.
                self.last_update[key] = time.time()

                try:
                    status = device.get_ac_status()
                except Exception as e:
                    # One unreachable AC must not abort the poll cycle for the
                    # remaining devices, so failures are handled per device.
                    logger.warning("Polling device %s (%s) failed: %s" % (
                        device.name or key, key, e))
                    status = None

                # Availability is keyed by the MAC used in the state/discovery
                # topics, which may differ in case from the config entry.
                mac = device.status.get('macaddress') or key

                if status:
                    self._set_device_available(mac, True)
                    self.publish_mqtt_info(status)

                else:
                    logger.debug("No status from device %s" % key)
                    self._set_device_available(mac, False)

        except Exception as e:
            logger.critical(e)
            logger.debug(traceback.format_exc())
            # Something went wrong.....

        return 1

    def dump_homeassistant_config_from_devices(self, devices):

        if devices == {}:
            print("No devices defined")
            sys.exit()

        devices_array = self.make_devices_array_from_devices(devices)
        if devices_array == {}:
            print("something went wrong, no devices found")
            sys.exit()

        print("**************** Start copy below ****************")
        a = []
        for key in devices_array:
            # Echo
            device = devices_array[key]
            device['platform'] = 'mqtt'
            a.append(device)
        print(yaml.dump({'climate': a}))
        print("**************** Stop copy above ****************")

    def make_devices_array_from_devices(self, devices):

        devices_array = {}

        for device in devices.values():
            # topic = self.config["mqtt_auto_discovery_topic"]+"/climate/"+device.status["macaddress"]+"/config"
            name = ""
            if not device.name:
                name = device.status["macaddress"]
            else:
                name = device.name.encode('ascii', 'ignore')

            device_array = {
                # ,"power_command_topic" : self.config["mqtt_topic_prefix"]+  device.status["macaddress"]+"/power/set"
                "name": str(name.decode("utf-8")), "mode_command_topic": self.config["mqtt_topic_prefix"] + device.status["macaddress"]+"/mode_homeassistant/set", "temperature_command_topic": self.config["mqtt_topic_prefix"] + device.status["macaddress"]+"/temp/set", "fan_mode_command_topic": self.config["mqtt_topic_prefix"] + device.status["macaddress"]+"/fanspeed_homeassistant/set", "swing_mode_command_topic": self.config["mqtt_topic_prefix"] + device.status["macaddress"] + "/fixation_v/set", "action_topic": self.config["mqtt_topic_prefix"] + device.status["macaddress"]+"/homeassistant/set"                # Read values
                , "current_temperature_topic": self.config["mqtt_topic_prefix"] + device.status["macaddress"]+"/ambient_temp/value", "mode_state_topic": self.config["mqtt_topic_prefix"] + device.status["macaddress"]+"/mode_homeassistant/value", "temperature_state_topic": self.config["mqtt_topic_prefix"] + device.status["macaddress"]+"/temp/value", "fan_mode_state_topic": self.config["mqtt_topic_prefix"] + device.status["macaddress"]+"/fanspeed_homeassistant/value", "swing_mode_state_topic": self.config["mqtt_topic_prefix"] + device.status["macaddress"]+"/fixation_v/value", "fan_modes": ["Auto", "Low", "Medium", "Medium_High", "High", "Turbo", "Mute"]                # @Anonym-tsk
                , "modes": ["off", "cool", "heat", "fan_only", "dry"], "swing_modes": ["TOP", "MIDDLE1", "MIDDLE2", "MIDDLE3", "BOTTOM", "SWING",  "AUTO"], "max_temp": 32.0, "min_temp": 16.0, "precision": 0.5, "temp_step": 0.5, "unique_id": device.status["macaddress"], "device": {"ids": device.status["macaddress"], "name": str(name.decode("utf-8")), "model": 'Aircon', "mf": "Broadlink", "sw": broadlink.version}, "pl_avail": "online", "pl_not_avail": "offline", "availability_mode": "all", "availability": [{"topic": self.config["mqtt_topic_prefix"] + "LWT"}, {"topic": self._device_availability_topic(device.status["macaddress"])}]
            }

            devices_array[device.status["macaddress"]] = device_array

        return devices_array

    def publish_mqtt_auto_discovery(self, devices):
        if devices == [] or devices == None:
            print("No devices defined")
            logger.error(
                "No Devices defined, either enable discovery or add them to config")
            sys.exit()

        # Make an array
        devices_array = self.make_devices_array_from_devices(devices)
        if devices_array == {}:
            print("something went wrong, no devices found")
            sys.exit()

        # If retain is set for MQTT, then retain it
        if (self.config["mqtt_auto_discovery_topic_retain"]):
            retain = self.config["mqtt_auto_discovery_topic_retain"]

        else:
            retain = False

        logger.debug("HA config Retain set to: " + str(retain))

        # Loop da loop all devices and publish discovery settings
        for key in devices_array:
            device = devices_array[key]
            topic = self.config["mqtt_auto_discovery_topic"] + \
                "/climate/"+key+"/config"
            # Publish
            self._publish(topic, json.dumps(device), retain=retain)

    def publish_mqtt_info(self, status, force_update=False):
        # If auto discovery is used, then always update
        if not force_update:
            force_update = True if "mqtt_auto_discovery_topic" in self.config and self.config[
                "mqtt_auto_discovery_topic"] else False

        logger.debug("Force update is: " + str(force_update))

        # Publish all values in status
        for key in status:
            # Make sure its a string
            value = status[key]

            # check if device already in previous_status
            if not force_update and status['macaddress'] in self.previous_status:
                # Check if key in state
                if key in self.previous_status[status['macaddress']]:
                    # If the values are same, skip it to make mqtt less chatty #17

                    if self.previous_status[status['macaddress']][key] == value:
                        # print ("value same key:%s, value:%s vs : %s" %  (key,value,self.previous_status[status['macaddress']][key]))
                        continue
                    else:
                        ""
                        # print ("value NOT Same key:%s, value:%s vs : %s" %  (key,value,self.previous_status[status['macaddress']][key]))

            pubResult = self._publish(
                self.config["mqtt_topic_prefix"] + status['macaddress']+'/'+key + '/value', value)

            if pubResult != None:
                logger.warning('Publishing Result: "%s"' %
                               mqtt.error_string(pubResult))
                if pubResult == mqtt.MQTT_ERR_NO_CONN:
                    self.connect_mqtt()

                break

        # Set previous to current
        self.previous_status[status['macaddress']] = status

        return

        # self._publish(binascii.hexlify(status['macaddress'])+'/'+ 'temp/value',status['temp']);

    def _publish(self, topic, value, retain=False, qos=0):
        payload = value
        logger.debug('publishing on topic "%s", data "%s"' % (topic, payload))
        pubResult = self._mqtt.publish(
            topic, payload=payload, qos=qos, retain=retain)

        # If there error, then debug log and return not None
        if pubResult[0] != 0:
            logger.debug('Publishing Result: "%s"' %
                         mqtt.error_string(pubResult[0]))
            return pubResult[0]

    def _publish_online(self):
        # Heartbeat on the LWT availability topic. The will publishes "offline"
        # on an ungraceful disconnect; re-publishing "online" here (and on every
        # poll) means a stray "offline" is corrected within one update interval
        # instead of waiting for a full reconnect to fire _on_mqtt_connect.
        self._publish(self.config["mqtt_topic_prefix"] +
                      'LWT', 'online', retain=True)

    def _device_availability_topic(self, mac):
        return self.config["mqtt_topic_prefix"] + mac + "/availability"

    def _publish_device_availability(self, mac, state):
        self._publish(self._device_availability_topic(mac), state, retain=True)

    def _set_device_available(self, mac, available):
        # The LWT only covers the bridge's own MQTT connection, so a device
        # that stops answering on its IP would otherwise stay "available" in
        # Home Assistant forever. Publish per-device availability instead,
        # but only on a state change to keep MQTT traffic low.
        if available:
            self._device_failures[mac] = 0
            if self._device_available.get(mac) is True:
                return
            self._device_available[mac] = True
            logger.info("Device %s is available" % mac)
            self._publish_device_availability(mac, 'online')
            return

        failures = self._device_failures.get(mac, 0) + 1
        self._device_failures[mac] = failures
        threshold = self.config.get("availability_failures") or 3
        if failures < threshold:
            logger.debug("Device %s failed %d/%d poll(s)" %
                         (mac, failures, threshold))
            return
        if self._device_available.get(mac) is False:
            return
        self._device_available[mac] = False
        logger.warning("Device %s did not respond to %d consecutive polls, publishing offline" % (
            mac, failures))
        self._publish_device_availability(mac, 'offline')

    def connect_mqtt(self):

        # Only build the client once and reuse it (and its network thread).
        # Building a NEW client on every reconnect attempt uses the same
        # client_id, which makes the broker evict the previous connection.
        # That in turn fails the next publish, triggering another reconnect,
        # an endless "not currently connected" flap plus a client/thread leak.
        if self._mqtt is not None:
            if not self._mqtt.is_connected():
                logger.warning(
                    "MQTT not currently connected; relying on paho auto-reconnect for %s" % self.config["mqtt_host"])
            return

        # Setup client
        self._mqtt = mqtt.Client(
            client_id=self.config["mqtt_client_id"], clean_session=True, userdata=None)

        # Set last will and testament
        self._mqtt.will_set(
            self.config["mqtt_topic_prefix"]+"LWT", "offline", True)

        # Auth
        if self.config["mqtt_user"] and self.config["mqtt_password"]:
            self._mqtt.username_pw_set(
                self.config["mqtt_user"], self.config["mqtt_password"])

        # Setup callbacks
        self._mqtt.on_connect = self._on_mqtt_connect
        self._mqtt.on_message = self._on_mqtt_message
        self._mqtt.on_log = self._on_mqtt_log
        self._mqtt.on_subscribed = self._mqtt_on_subscribe

        # Have paho auto-reconnect in its loop thread so a transient loss of
        # connection (e.g. broker restart) does not need manual reconnect calls.
        self._mqtt.reconnect_delay_set(min_delay=1, max_delay=30)

        # Connect
        logger.debug("Coneccting to MQTT: %s with client ID = %s" %
                     (self.config["mqtt_host"], self.config["mqtt_client_id"]))
        self._mqtt.connect(
            self.config["mqtt_host"], port=self.config["mqtt_port"], keepalive=60, bind_address="")

        # Start
        # creates new thread and runs Mqtt.loop_forever() in it.
        self._mqtt.loop_start()

    def _on_mqtt_log(self, client, userdata, level, buf):

        if level == mqtt.MQTT_LOG_ERR:
            logger.debug("Mqtt log: " + buf)

    def _mqtt_on_subscribe(self, client, userdata, mid, granted_qos):
        logger.debug("Mqtt Subscribed")

    def _on_mqtt_message(self, client, userdata, msg):
        # A command sent to an unreachable AC raises from the UDP layer. If that
        # escaped this callback it would kill paho's network loop thread, so
        # contain it here and keep the bridge (and its reconnects) alive.
        try:
            self._handle_mqtt_message(client, userdata, msg)
        except Exception as e:
            logger.error("Error handling message on %s: %s" % (msg.topic, e))
            logger.debug(traceback.format_exc())

    def _handle_mqtt_message(self, client, userdata, msg):

        try:
            logger.debug('Mqtt Message Received! Userdata: %s, Message %s' % (
                userdata, msg.topic+" "+str(msg.payload)))
            # Function is second last .. decode to str #43
            function = str(msg.topic.split('/')[-2])
            address = msg.topic.split('/')[-3]
            # Make sure its proper STR .. python3  #43 .. very
            address = address.encode('ascii', 'ignore').decode("utf-8")
            # 43 decode to force to str
            value = str(msg.payload.decode("ascii"))
            logger.debug('Mqtt decoded --> Function: %s, Address: %s, value: %s' %
                         (function, address, value))

        except Exception as e:
            logger.critical(e)
            return

        # Process received        ##Probably need to exit here as well if command not send, but should exit on status update above .. grr, hate stupid python
        if function == "temp":
            try:
                if self.device_objects.get(address):
                    status = self.device_objects[address].set_temperature(
                        float(value))

                    if status:
                        self.publish_mqtt_info(status)
                else:
                    logger.debug("Device not on list of devices %s, type:%s" % (
                        address, type(address)))
                    return
            except Exception as e:
                logger.critical(e)
                return

        elif function == "power":
            if value.lower() == "on":
                status = self.device_objects[address].switch_on()
                if status:
                    self.publish_mqtt_info(status)
            elif value.lower() == "off":
                status = self.device_objects[address].switch_off()
                if status:
                    self.publish_mqtt_info(status)
            else:
                logger.debug(
                    "Switch has invalid value, values is on/off received %s", value)
                return

        elif function == "mode":

            status = self.device_objects[address].set_mode(value)
            if status:
                self.publish_mqtt_info(status)

            else:
                logger.debug("Mode has invalid value %s", value)
                return

        elif function == "fanspeed":
            if value.lower() == "turbo":
                status = self.device_objects[address].set_turbo("ON")

                # status = self.device_objects[address].set_mute("OFF")
            elif value.lower() == "mute":
                status = self.device_objects[address].set_mute("ON")

            else:
                # status = self.device_objects[address].set_mute("ON")
                # status = self.device_objects[address].set_turbo("OFF")
                status = self.device_objects[address].set_fanspeed(value)

            if status:
                self.publish_mqtt_info(status)

            else:
                logger.debug("Fanspeed has invalid value %s", value)
                return

        elif function == "fanspeed_homeassistant":
            if value.lower() == "turbo":
                status = self.device_objects[address].set_turbo("ON")

                # status = self.device_objects[address].set_mute("OFF")
            elif value.lower() == "mute":
                status = self.device_objects[address].set_mute("ON")

            else:
                # status = self.device_objects[address].set_mute("ON")
                # status = self.device_objects[address].set_turbo("OFF")
                status = self.device_objects[address].set_fanspeed(value)

            if status:
                self.publish_mqtt_info(status)

            else:
                logger.debug(
                    "Fanspeed_homeassistant has invalid value %s", value)
                return

        elif function == "mode_homekit":

            status = self.device_objects[address].set_homekit_mode(value)
            if status:
                self.publish_mqtt_info(status)

            else:
                logger.debug("Mode_homekit has invalid value %s", value)
                return
        elif function == "mode_homeassistant":

            status = self.device_objects[address].set_homeassistant_mode(value)
            if status:
                self.publish_mqtt_info(status)

            else:
                logger.debug("Mode_homeassistant has invalid value %s", value)
                return
        elif function == "state":

            if value == "refresh":
                logger.debug("Refreshing states")
                status = self.device_objects[address].get_ac_status()
            else:
                logger.debug("Command not valid: " + value)
                return

            if status:
                self.publish_mqtt_info(status, force_update=True)
            else:
                logger.debug("Unable to refresh")
                return
            return
        elif function == "fixation_v":
            try:
                if self.device_objects.get(address):
                    status = self.device_objects[address].set_fixation_v(value)

                    if status:
                        self.publish_mqtt_info(status)
                else:
                    logger.debug("Device not on list of devices %s, type:%s" % (
                        address, type(address)))
                    return
            except Exception as e:
                logger.critical(e)
                return
        elif function == "fixation_h":
            try:
                if self.device_objects.get(address):
                    status = self.device_objects[address].set_fixation_h(value)
                    if status:
                        self.publish_mqtt_info(status)
                else:
                    logger.debug("Device not on list of devices %s, type:%s" % (
                        address, type(address)))
                    return
            except Exception as e:
                logger.critical(e)
                return
        elif function == "display":
            try:
                if self.device_objects.get(address):
                    status = self.device_objects[address].set_display(value)
                    if status:
                        self.publish_mqtt_info(status)
                else:
                    logger.debug("Device not on list of devices %s, type:%s" % (
                        address, type(address)))
                    return
            except Exception as e:
                logger.critical(e)
                return
        elif function == "mildew":
            try:
                if self.device_objects.get(address):
                    status = self.device_objects[address].set_mildew(value)
                    if status:
                        self.publish_mqtt_info(status)
                else:
                    logger.debug("Device not on list of devices %s, type:%s" % (
                        address, type(address)))
                    return
            except Exception as e:
                logger.critical(e)
                return
        elif function == "clean":
            try:
                if self.device_objects.get(address):
                    status = self.device_objects[address].set_clean(value)
                    if status:
                        self.publish_mqtt_info(status)
                else:
                    logger.debug("Device not on list of devices %s, type:%s" % (
                        address, type(address)))
                    return
            except Exception as e:
                logger.critical(e)
                return
        elif function == "health":
            try:
                if self.device_objects.get(address):
                    status = self.device_objects[address].set_health(value)
                    if status:
                        self.publish_mqtt_info(status)
                else:
                    logger.debug("Device not on list of devices %s, type:%s" % (
                        address, type(address)))
                    return
            except Exception as e:
                logger.critical(e)
                return
        elif function == "sleep":
            try:
                if self.device_objects.get(address):
                    status = self.device_objects[address].set_sleep(value)
                    if status:
                        self.publish_mqtt_info(status)
                else:
                    logger.debug("Device not on list of devices %s, type:%s" % (
                        address, type(address)))
                    return
            except Exception as e:
                logger.critical(e)
                return
        else:
            logger.debug("No function match")
            return

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """
        RC definition:
        0: Connection successful
        1: Connection refused - incorrect protocol version
        2: Connection refused - invalid client identifier
        3: Connection refused - server unavailable
        4: Connection refused - bad username or password
        5: Connection refused - not authorised
        6-255: Currently unused.
        """

        logger.debug('Mqtt connected! client=%s, userdata=%s, flags=%s, rc=%s' % (
            client, userdata, flags, rc))
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        sub_topic = self.config["mqtt_topic_prefix"] + "+/+/set"
        client.subscribe(sub_topic)
        logger.debug('Listing on %s for messages' % (sub_topic))

        # LWT
        self._publish_online()

        # A reconnect may have followed a broker restart that dropped retained
        # messages, so republish each device's availability on its next poll.
        self._device_available = {}
