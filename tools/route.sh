#!/bin/bash

FLIGHT=$1

flightInfo=`curl -s https://api.adsbdb.com/v0/callsign/${FLIGHT}`
if echo "$flightInfo" | jq -e '.response | type == "string"' >/dev/null 2>&1; then
    echo "ERROR: no flightroute in response from server - $flightInfo"
    exit 1
elif echo "$flightInfo" | jq -e '.response | type != "object"' >/dev/null 2>&1; then
    echo "ERROR: invalid response from server - $flightInfo"
    exit 1
fi

echo $flightInfo | jq -r '.response.flightroute | .origin.name + " (" + .origin.iata_code + ") -> " + .destination.name + " (" + .destination.iata_code + ")"'
