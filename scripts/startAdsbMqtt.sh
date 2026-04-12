#!/bin/bash
#
# Script to start the ADS-B MQTT publisher
#
# Usage: ${0} [<distance> [<logLevel>] [<options>]]]

DISTANCE="${1:-2.0}"
LOG_LEVEL="${2:-WARNING}"
OPTIONS="${3}"  # e.g., '-vvv'

SCRIPT_PATH="${HOME}/Code/ADSBMonitor/adsbmon"
CONF_FILE_PATH="${HOME}/Code/ADSBMonitor/adsbmon"

python3 ${SCRIPT_PATH}/adsbmon.py -c ${CONF_FILE_PATH}/config.yaml ${OPTIONS} -L ${LOG_LEVEL} -D ${DISTANCE} /run/readsb/
