#!/usr/bin/python3
#
# Object that provides the basic ability to connect to an MQTT broker and
#  publish messages to it

import json
import logging

import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion


class BaseMqtt:
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

        self.client.on_connect = BaseMqtt._onMqttConnect

        if self.client.connect(self.host, self.port, self.keepalive) != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError("Failed to connect to MQTT broker at %s:%s", self.host, self.port)
        if self.client.loop_start() != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError("Failed to start the MQTT polling loop")
        logging.debug("MQTT Client initialized successfully")

    def publishJson(self, topic, msg, retain=False):
        ''' Publish the given JSON message.
            Returns MQTTMessageInfo so that the caller can do .wait_for_publish()
             on the message.
        '''
        if isinstance(msg, str):
            jsonPayload = msg
        else:
            jsonPayload = json.dumps(msg)
        logging.debug("On topic '%s', Publish '%s', Retain='%d'", topic, jsonPayload, retain)
        result = self.client.publish(topic, payload=jsonPayload, qos=1, retain=retain)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logging.info("Message sent to topic: %s", topic)
            logging.debug("Message: %s", jsonPayload)
        else:
            logging.warning("Failed to send message to topic: %s; error code: %d", topic, result.rc)
        return result
