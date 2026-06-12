#!/usr/bin/python3
#
# Cache-backed route lookups via the callsignServer web API.
#
# Flow per callsign:
#   GET http://<server>/callsign/{callsign}
#   -> airline, origin (icao, name, city, country, lat, lon), destination (same)
#
# Results are cached in-memory; only the first call per callsign hits the network.
# Airport codes returned by the server are ICAO; if they look like IATA codes,
# they are converted using an optional OurAirports CSV (iata_code -> ident).

import csv
import logging
import requests


ROUTE_SERVER = "http://192.168.166.13:5000"
REQUEST_TIMEOUT = 5


def loadIataToIcao(csvPath):
    mapping = {}
    try:
        with open(csvPath, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                iata = row.get('iata_code', '').strip()
                icao = row.get('ident', '').strip()
                if iata and icao:
                    mapping[iata] = icao
    except Exception as e:
        logging.warning("RouteDB: could not load airport CSV %s: %s", csvPath, e)
    return mapping


class RouteDB:
    def __init__(self, serverUrl=ROUTE_SERVER, airportCsv=None):
        self._serverUrl = serverUrl.rstrip('/')
        self._iataToIcao = loadIataToIcao(airportCsv) if airportCsv else {}
        self._routes = {}  # callsign -> enriched dict, or None (not found)

    def _toIcao(self, code):
        return self._iataToIcao.get(code, code)

    def getRoute(self, callsign):
        """Return route info dict for callsign, or None if unknown.

        Keys: origin_icao, origin_iata, origin, dest_icao, dest_iata, dest
        """
        if callsign not in self._routes:
            self._routes[callsign] = self._fetchRoute(callsign)
        return self._routes[callsign]

    def _fetchRoute(self, callsign):
        try:
            r = requests.get(f"{self._serverUrl}/callsign/{callsign}",
                             timeout=REQUEST_TIMEOUT)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
            if not data.get('found'):
                return None
            origin = data.get('origin') or {}
            dest = data.get('destination') or {}
            if not origin or not dest:
                return None
            origin_code = origin.get('icao', '')
            dest_code = dest.get('icao', '')
            return {
                'origin_icao': self._toIcao(origin_code),
                'origin_iata': origin_code,
                'origin':      origin.get('name', origin_code),
                'dest_icao':   self._toIcao(dest_code),
                'dest_iata':   dest_code,
                'dest':        dest.get('name', dest_code),
            }
        except Exception as e:
            logging.warning("RouteDB: fetch failed for %s: %s", callsign, e)
            return None
