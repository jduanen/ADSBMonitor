#!/bin/bash
#
# Script to print the retained messages for sensors from the HomeAssistant broker

MQTT_USER=$1
MQTT_PASSWD=$2

if [ $# -ne 2 ]; then
    echo "Usage: $0 <mqttUser> <mqttPassword>"
    exit 1
fi

mosquitto_sub -h 192.168.166.5 -p 1883 -u $MQTT_USER -P $MQTT_PASSWD --retained-only -v -t 'homeassistant/sensor/#'
