#!/bin/bash
#
# Script to remove orphaned vehicle entities on HA

HEX_CODES="$@"

for H in $HEX_CODES; do
  echo "Removing: $H"
  mosquitto_pub -h 192.168.166.5 -u $MQTT_USER -P $MQTT_PASSWD -t "homeassistant/sensor/adsb_${H}/config" -m "" -r
done
