#!/bin/bash
#
# Script to print the retained messages for sensors from the HomeAssistant broker

mqttUser="${1:-${MQTT_USER}}"
mqttPasswd="${2:-${MQTT_PASSWD}}"

OPTIONS= # "-v"

if [[ -z "$mqttUser" || -z "$mqttPasswd" ]]; then
    echo "Usage: $0 <mqttUser> <mqttPassword> {<options>}"
    exit 1
fi

mosquitto_sub -h 192.168.166.5 -p 1883 -u $mqttUser -P $mqttPasswd --retained-only ${OPTIONS}-t 'homeassistant/sensor/#' | jq '.'
