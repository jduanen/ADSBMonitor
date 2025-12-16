#!/usr/bin/python3
#
# Script to fetch aircraft track data from ADS-B Server
#

import requests
import hashlib
import json
import sys
import time


RASPI_IP="adsbrx.lan"
ADSB_URL = f"http://{RASPI_IP}/tar1090/data/aircraft.json"


lastHash = None


def fetchIfHashChanged(url):
    global lastHash

    resp = requests.get(url, timeout=5)
    dataHash = hashlib.md5(resp.content).hexdigest()

    if dataHash != lastHash:
        lastHash = dataHash
        data = resp.json()
        print(f"Changed: {len(data['aircraft'])} aircraft")
        return data
    return None

while True:
    data = fetchIfHashChanged(ADSB_URL)
    if data:
        json.dump(data, sys.stdout, indent=4, sort_keys=True)
    time.sleep(2)
