#!/usr/bin/python3
#
# Object that 

import json
import logging


class AdsbMqtt(BaseMqtt):
    def __init__(self, clientId, host, port, keepalive, username=None, password=None):
        super().__init__(clientId, host, port, keepalive, username, password)

    def publishServiceDiscoveryMsg(self):
        ''' Service discovery and state update
        '''
        topic = "homeassistant/binary_sensor/adsb_monitor/status/config"
        msg = {
            "name": "ADS-B Monitor",
            "device_class": "connectivity",
            "state_topic": "adsb/monitor/status",
            "payload_on": "online",
            "payload_off": "offline",
            "unique_id": "adsb_monitor_status",
            "device": {
                "identifiers": ["adsb_monitor"],
                "name": "ADS-B Receiver",
                "manufacturer": "Raspberry Pi 4B",
                "model": "FlightAware USB",
                "sw_version": "bookworm"
            },
            "origin": {
                "name": "adsbmon.py",
                "sw": f"{ADSB_MON_VERSION_MAJOR}.{ADSB_MON_VERSION_MINOR}"
            }
        }
        self.publishJson(topic, msg, retain=True)


def publishServiceStateMsg(online):
    topic = "adsb/monitor/status"
    msg = "online" if online else "offline"
    mqttClient.publishJson(topic, msg, retain=True)


# Track discovery, null discovery, and update
def publishTrackDiscoveryMsg(hexId):
    topic = f"homeassistant/sensor/adsb_{hexId}/config"
    msg = {
        "name": f"ADS-B Flight {hexId}",
        "unique_id": f"{hexId}",
        "state_topic": f"adsb/vehicles/{hexId}/state",
        "unit_of_measurement": "vehicles",
        "device": {
            "identifiers": [f"adsb_vehicle_{hexId}"],
            "name": f"Vehicle {hexId}",
        },
        "json_attributes_topic": f"adsb/vehicles/state",
        "value_template": "{{ value_json.icao24 }}",
        "device_class": None,
        "state_class": None,
        "origin": {
            "name": "adsbmon.py",
            "sw": f"{ADSB_MON_VERSION_MAJOR}.{ADSB_MON_VERSION_MINOR}"
        }
    }
    mqttClient.publishJson(topic, msg, retain=True)


def publishNullTrackDiscoveryMsg(hexId):
    topic = f"homeassistant/sensor/adsb_{hexId}/config"
    mqttClient.publishJson(topic, "", retain=True)


def publishTrackUpdateMsg(hexId, message):
    topic = f"adsb/vehicles/{hexId}/state"
    mqttClient.publishJson(topic, message)


# Tracks count discovery, null discovery, and update
def publishTracksCountDiscoveryMsg():
    topic = "homeassistant/sensor/adsb_monitor/count/config"
    msg = {
        "name": "ADS-B Monitor vehicles count",
        "state_topic": "adsb/monitor/count",
        "unique_id": "adsb_monitor_count",
        "unit_of_measurement": "vehicles",
        "device_class": None,
        "state_class": "measurement",
        "device": {
            "identifiers": ["adsb_monitor"],
            "name": "ADS-B Receiver",
            "manufacturer": "Raspberry Pi 4B",
            "model": "FlightAware USB",
            "sw_version": "bookworm"
        },
        "origin": {
            "name": "adsbmon.py",
            "sw": f"{ADSB_MON_VERSION_MAJOR}.{ADSB_MON_VERSION_MINOR}"
        }
    }
    mqttClient.publishJson(topic, msg, retain=True)


def publishNullTracksCountDiscoveryMsg():
    topic = "homeassistant/sensor/adsb_monitor/count/config"
    mqttClient.publishJson(topic, "", retain=True)


def publishTracksCountUpdateMsg(numTracks):
    topic = "adsb/monitor/count"
    msg = numTracks
    mqttClient.publishJson(topic, msg, retain=True)
