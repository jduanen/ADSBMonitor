#!/usr/bin/python3
#
# Object that extends the basic MQTT object to publish MQTT versions of the
#  ADS-B messages from readsb

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.BaseMqtt import BaseMqtt


class AdsbMqtt(BaseMqtt):
    def __init__(self, clientId, host, port, keepalive, username=None, password=None, version=""):
        super().__init__(clientId, host, port, keepalive, username, password)
        self.version = version

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
                "sw": self.version
            }
        }
        self.publishJson(topic, msg, retain=True)

    def publishServiceStateMsg(self, online):
        ''' ?
        '''
        topic = "adsb/monitor/status"
        msg = "online" if online else "offline"
        self.publishJson(topic, msg, retain=True)

    def publishTrackDiscoveryMsg(self, hexId):
        ''' Track discovery, null discovery, and update
        '''
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
            "json_attributes_topic": "adsb/vehicles/state",
            "value_template": "{{ value_json.icao24 }}",
            "device_class": None,
            "state_class": None,
            "origin": {
                "name": "adsbmon.py",
                "sw": self.version
            }
        }
        self.publishJson(topic, msg, retain=True)

    def publishNullTrackDiscoveryMsg(self, hexId):
        ''' ?
        '''
        topic = f"homeassistant/sensor/adsb_{hexId}/config"
        self.publishJson(topic, "", retain=True)

    def publishTrackUpdateMsg(self, hexId, message):
        ''' ?
        '''
        topic = f"adsb/vehicles/{hexId}/state"
        self.publishJson(topic, message)

    def publishTracksCountDiscoveryMsg(self):
        ''' Tracks count discovery, null discovery, and update
        '''
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
                "sw": self.version
            }
        }
        self.publishJson(topic, msg, retain=True)

    def publishNullTracksCountDiscoveryMsg(self):
        ''' ?
        '''
        topic = "homeassistant/sensor/adsb_monitor/count/config"
        self.publishJson(topic, "", retain=True)

    def publishTracksCountUpdateMsg(self, numTracks):
        ''' ?
        '''
        topic = "adsb/monitor/count"
        msg = numTracks
        self.publishJson(topic, msg, retain=True)
