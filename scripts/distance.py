#!/usr/bin/python3

import math


def distanceNm(lat1, lon1, lat2, lon2):
    """
    Distance between two WGS84 coordinates in nautical miles.
    lat/lon in decimal degrees
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

    # Distance in km
    d_km = R_km * c

    # Convert km to nautical miles (1 NM = 1.852 km)
    d_nm = d_km / 1.852
    return d_nm


def d(lat, lon):
    RECEIVER_LAT=37.4599669
    RECEIVER_LON=-122.1652244
    print(distanceNm(RECEIVER_LAT, RECEIVER_LON, lat, lon))
