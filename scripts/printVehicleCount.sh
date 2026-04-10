#!/bin/bash
#
# Script to print count of ADS-B vehicles within the range of interest

MQTT_USER=$1
MQTT_PASSWD=$2
OPTIONS=$3  # e.g., '-v'

if [ $# -lt 2 ]; then
    echo "Usage: $0 <mqttUser> <mqttPassword> {<options>}"
    exit 1
fi

mosquitto_sub -h 192.168.166.5 -p 1883 -u $MQTT_USER -P $MQTT_PASSWD ${OPTIONS} -t 'adsb/monitor/in_range'
