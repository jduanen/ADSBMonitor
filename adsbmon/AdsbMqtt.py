#!/usr/bin/python3
#
# Object that extends the basic MQTT object to publish MQTT versions of the
#  ADS-B messages from readsb
#
# MQTT publish topics:
#  * publishServiceDiscoveryMsg:          "homeassistant/binary_sensor/adsb_monitor/status/config"
#  * publishServiceStateMsg:              "adsb/monitor/status"
#  * publishTrackDiscoveryMsg:            f"homeassistant/sensor/adsb_{message['hex']}/config"
#  * publishNullTrackDiscoveryMsg:        f"homeassistant/sensor/adsb_{message['hex']}/config"
#  * publishTrackUpdateMsg:               f"adsb/vehicles/{message['hex']}/state"
#  * publishTracksCountDiscoveryMsg:      "homeassistant/sensor/adsb_monitor/count/config"
#  * publishNullTracksCountDiscoveryMsg:  "homeassistant/sensor/adsb_monitor/count/config"
#  * publishTracksCountUpdateMsg:         "adsb/monitor/count"
#  * publishTrackingCountDiscoveryMsg:    "homeassistant/sensor/adsb_monitor/tracking/config"
#  * publishTrackingCountNullMsg:         "homeassistant/sensor/adsb_monitor/tracking/config"
#  * publishTrackingCountUpdateMsg:       "adsb/monitor/tracking"
#

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.BaseMqtt import BaseMqtt


MSG_DEVICE = {
    "identifiers": ["adsb_monitor"],
    "name": "ADS-B Receiver",
    "manufacturer": "Raspberry Pi 4B",
    "model": "FlightAware USB",
    "sw_version": "bookworm"
}


class AdsbMqtt(BaseMqtt):
    def __init__(self, clientId, host, port, keepalive, username=None, password=None, version=""):
        super().__init__(clientId, host, port, keepalive, username, password)
        self.version = version

    def publishServiceDiscoveryMsg(self):
        topic = "homeassistant/binary_sensor/adsb_monitor/status/config"
        msg = {
            "name": "ADS-B Monitor",
            "device_class": "connectivity",
            "state_topic": "adsb/monitor/status",
            "payload_on": "online",
            "payload_off": "offline",
            "unique_id": "adsb_monitor_status",
            "device": MSG_DEVICE,
            "origin": {
                "name": self.__class__.__name__,
                "sw": self.version
            }
        }
        self.publishJson(topic, msg, retain=True)

    def publishServiceStateMsg(self, online):
        topic = "adsb/monitor/status"
        msg = "online" if online else "offline"
        self.publishJson(topic, msg, retain=True)

    def publishTrackDiscoveryMsg(self, hexId, trackName):
        topic = f"homeassistant/sensor/adsb_{hexId}/config"
        msg = {
            "name": trackName,
            "unique_id": f"adsb_{hexId}",
            "state_topic": f"adsb/vehicles/{hexId}/state",
            "value_template": "{{ value_json.track_name | trim }}",
            "json_attributes_topic": f"adsb/vehicles/{hexId}/state",
            "json_attributes_template": "{{ value_json | tojson }}",
            "device": {
                "identifiers": [f"adsb_vehicle_{hexId}"],
                "name": f"ADS-B {hexId}",
            },
            "device_class": None,
            "state_class": None,
            "origin": {
                "name": "adsbmon.py",
                "sw": self.version
            }
        }
        self.publishJson(topic, msg, retain=True)

    def publishNullTrackDiscoveryMsg(self, hexId):
        topic = f"homeassistant/sensor/adsb_{hexId}/config"
        self.publishJson(topic, "", retain=True)

    def publishTrackUpdateMsg(self, hexId, message):
        topic = f"adsb/vehicles/{hexId}/state"
        self.publishJson(topic, message, retain=False)

    def publishTracksCountDiscoveryMsg(self):
        topic = "homeassistant/sensor/adsb_monitor/count/config"
        msg = {
            "name": "ADS-B Monitor vehicles count",
            "state_topic": "adsb/monitor/count",
            "unique_id": "adsb_monitor_count",
            "unit_of_measurement": "vehicles",
            "device_class": None,
            "state_class": "measurement",
            "device": DEVICE,
            "origin": {
                "name": self.__class__.__name__,
                "sw": self.version
            }
        }
        self.publishJson(topic, msg, retain=True)

    def publishNullTracksCountDiscoveryMsg(self):
        topic = "homeassistant/sensor/adsb_monitor/count/config"
        self.publishJson(topic, "", retain=True)

    def publishTracksCountUpdateMsg(self, numTracks):
        topic = "adsb/monitor/count"
        msg = numTracks
        self.publishJson(topic, msg, retain=True)

    def publishTrackingCountDiscoveryMsg(self):
        topic = "homeassistant/sensor/adsb_monitor/tracking/config"
        msg = {
            "name": "ADS-B Monitor vehicles tracking count",
            "state_topic": "adsb/monitor/tracking",
            "unique_id": "adsb_monitor_tracking",
            "unit_of_measurement": "vehicles",
            "device_class": None,
            "state_class": "measurement",
            "device": DEVICE,
            "origin": {
                "name": self.__class__.__name__,
                "sw": self.version
            }
        }
        self.publishJson(topic, msg, retain=True)

    def publishTrackingCountNullMsg(self):
        topic = "homeassistant/sensor/adsb_monitor/tracking/config"
        self.publishJson(topic, "", retain=True)

    def publishTrackingCountUpdateMsg(self, numTracks):
        topic = "adsb/monitor/tracking"
        msg = numTracks
        self.publishJson(topic, msg, retain=True)
