#!/usr/bin/python3
#
# Object that encapsulates information about the receiver site

import json
import math
from pprint import pprint
import sys
import time


class ReceiverSite:
    def __init__(self, name, max2dDistance, latitude, longitude, altitude):
        self.name = name
        self.max2dDistance = max2dDistance
        self.lat = latitude
        self.lon = longitude
        self.alt = altitude

    def print(self):
        state = {
            'name': self.name,
            'maxDistance': self.max2dDistance,
            'location': {
                'latitude': self.lat,
                'longitude': self.lon,
                'altitude': self.alt
            }
        }
        pprint(state, width=1, sort_dicts=False)

    def _distanceNM(self, lat1, lon1, lat2, lon2):
        """ Distance between two WGS84 coordinates in nautical miles.
            lat/lon is given in decimal degrees
        """
        # Earth radius in kilometers (mean)
        R_km = 6371.0088

        # Convert degrees to radians
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        # Haversine formula
        a = (math.sin(dphi / 2) ** 2 +
             math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        d_km = R_km * c  # Distance in km

        # convert km to nautical miles (1 NM = 1.852 km)
        d_nm = d_km / 1.852
        return d_nm

    def distance2dNM(self, lat, lon):
        return self._distanceNM(self.lat, self.lon, lat, lon)

    def distance3dNM(self, lat, lon, alt):
        return None
