#!/bin/bash
#
# Script to print count of ADS-B vehicles detected by the receiver

mqttUser="${1:-${MQTT_USER}}"
mqttPasswd="${2:-${MQTT_PASSWD}}"
OPTIONS=$3  # e.g., '-v' to print the topic

if [[ -z "$mqttUser" || -z "$mqttPasswd" ]]; then
    echo "Usage: $0 <mqttUser> <mqttPassword> {<options>}"
    exit 1
fi

mosquitto_sub -h 192.168.166.5 -p 1883 -u $mqttUser -P $mqttPasswd $OPTIONS -t 'adsb/monitor/count'
