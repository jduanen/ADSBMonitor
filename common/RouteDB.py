#!/usr/bin/python3
#
# Cache-backed route and airport lookups via hexdb.io (no API key required).
#
# Flow per callsign:
#   1. GET https://hexdb.io/api/v1/route/icao/{callsign}  -> "KDCA-KIAH"
#   2. GET https://hexdb.io/api/v1/airport/icao/{KDCA}   -> name, IATA code
#   3. GET https://hexdb.io/api/v1/airport/icao/{KIAH}   -> name, IATA code
#
# All results are cached in-memory; only the first call per callsign/airport
# hits the network.  Lookups are synchronous — callers block briefly on first
# encounter of a new callsign (bounded by REQUEST_TIMEOUT).

import logging
import requests


HEXDB_BASE = "https://hexdb.io/api/v1"
REQUEST_TIMEOUT = 5


class RouteDB:
    def __init__(self):
        self._routes = {}    # callsign -> enriched dict, or None (not found)
        self._airports = {}  # ICAO code  -> airport dict, or None (not found)

    def _fetchRoute(self, callsign):
        try:
            r = requests.get(f"{HEXDB_BASE}/route/icao/{callsign}",
                             timeout=REQUEST_TIMEOUT)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
            route_str = data.get('route', '')
            if not route_str or '-' not in route_str:
                return None
            parts = route_str.split('-')
            return {'origin_icao': parts[0], 'dest_icao': parts[-1]}
        except Exception as e:
            logging.warning("RouteDB: route fetch failed for %s: %s", callsign, e)
            return None

    def _fetchAirport(self, icao_code):
        try:
            r = requests.get(f"{HEXDB_BASE}/airport/icao/{icao_code}",
                             timeout=REQUEST_TIMEOUT)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
            return {
                'name': data.get('airport', icao_code),
                'iata': data.get('iata', icao_code),
            }
        except Exception as e:
            logging.warning("RouteDB: airport fetch failed for %s: %s", icao_code, e)
            return None

    def _getAirport(self, icao_code):
        if icao_code not in self._airports:
            self._airports[icao_code] = self._fetchAirport(icao_code)
        return self._airports[icao_code]

    def getRoute(self, callsign):
        """Return route info dict for callsign, or None if unknown.

        Keys: origin_icao, origin_iata, origin, dest_icao, dest_iata, dest
        """
        if callsign not in self._routes:
            raw = self._fetchRoute(callsign)
            if raw:
                origin = self._getAirport(raw['origin_icao']) or {}
                dest = self._getAirport(raw['dest_icao']) or {}
                self._routes[callsign] = {
                    'origin_icao': raw['origin_icao'],
                    'origin_iata': origin.get('iata', raw['origin_icao']),
                    'origin': origin.get('name', raw['origin_icao']),
                    'dest_icao': raw['dest_icao'],
                    'dest_iata': dest.get('iata', raw['dest_icao']),
                    'dest': dest.get('name', raw['dest_icao']),
                }
            else:
                self._routes[callsign] = None
        return self._routes[callsign]
