#!/usr/bin/python3
#
# Object that encapsulates a vehicle track

import json
import logging

import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion


class MyMqtt:
    @staticmethod
    def _onMqttConnect(client, userdata, flags, rc, properties=None):
        if rc != 0:
            logging.error("MQTT connection failed with result code: %s", rc)
            return True
        logging.info("Connected to MQTT broker successfully")
#        # 100ms delay for connection to settle and then publish discovery message(s)
#        threading.Timer(0.1, publishHaDiscovery(client))
        return False

    def __init__(self, clientId, host, port, keepalive, username=None, password=None):
        self.clientId = clientId
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.username = username
        self.password = password

        self.client = mqtt.Client(client_id=self.clientId, callback_api_version=CallbackAPIVersion.VERSION2)

        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        self.client.on_connect = MyMqtt._onMqttConnect

        if self.client.connect(self.host, self.port, self.keepalive) != mqtt.MQTT_ERR_SUCCESS:
            logging.error("Failed to connect to %s on port %d", self.host, self.port)
            return None
        if self.client.loop_start() != mqtt.MQTT_ERR_SUCCESS:
            logging.error("Failed to start the MQTT polling loop")
            return None
        logging.debug("MQTT Client initialized successfully")

    def publishJson(self, topic, msg, retain=False):
        if isinstance(msg, str):
            jsonPayload = msg
        else:
            jsonPayload = json.dumps(msg)
        logging.debug("On topic '%s', Publish '%s', Retain='%d'", topic, jsonPayload, retain)
        result = self.client.publish(topic, payload=jsonPayload, qos=1, retain=retain)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logging.info("Message sent to topic: %s", topic)
        else:
            logging.warning("Failed to send message to topic: %s; error code: %d", topic, result.rc)
