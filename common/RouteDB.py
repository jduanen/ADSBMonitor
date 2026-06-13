#!/usr/bin/python3
#
# Cache-backed route lookups via the callsignServer web API.
#
# Flow per callsign:
#   GET http://<server>/callsign/{callsign}
#   -> airline, origin (icao, name, city, country, lat, lon), destination (same)
#
# Lookups are non-blocking: getRoute() returns None immediately on a cache miss
# and fires a background thread to fetch and cache the result. The next call for
# the same callsign (typically ~1s later when the aircraft is still visible)
# returns the cached result.
#
# Airport codes returned by the server are both ICAO and IATA codes,

import csv
import logging
import threading
import requests


ROUTE_SERVER = "http://192.168.166.13:5000"
REQUEST_TIMEOUT = 10


class RouteDB:
    def __init__(self, serverUrl=ROUTE_SERVER):
        self._serverUrl = serverUrl.rstrip('/')
        self._routes = {}   # callsign -> enriched dict or None (lookup complete)
        self._pending = set()  # callsigns with an in-flight background fetch
        self._lock = threading.Lock()

    def getRoute(self, callsign):
        """Return cached route dict for callsign, or None if unknown/pending.

        On the first call for an unseen callsign, fires a background fetch and
        returns None. Subsequent calls return the result once the fetch completes.

        Keys when found: origin_icao, origin_iata, origin, dest_icao, dest_iata, dest
        """
        with self._lock:
            if callsign in self._routes:
                return self._routes[callsign]
            if callsign not in self._pending:
                self._pending.add(callsign)
                threading.Thread(target=self._bgFetch, args=(callsign,),
                                 daemon=True).start()
        return None

    def _bgFetch(self, callsign):
        result = self._fetchRoute(callsign)
        with self._lock:
            self._routes[callsign] = result
            self._pending.discard(callsign)

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
            return {
                'origin_icao': origin.get('icao', '?'),
                'origin_iata': origin.get('iata', '?'),
                'origin_name': origin.get('name', '?'),
                'dest_icao': dest.get('icao', '?'),
                'dest_iata': dest.get('iata', '?'),
                'dest_name': dest.get('name', '?')
            }
        except Exception as e:
            logging.warning("RouteDB: fetch failed for %s: %s", callsign, e)
            return None
