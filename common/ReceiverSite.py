#!/usr/bin/python3
#
# Object that encapsulates information about the receiver site and provides
#  functions for dealing with distance conversions and constraints.

from collections import namedtuple
import logging
import math
from pprint import pformat

from geographiclib.geodesic import Geodesic


FEET_PER_NM = 6076.115
METER_PER_NM = 1852.0
KM_PER_NM = METER_PER_NM / 1000.0

R_km = 6371.0088  # Earth radius in kilometers (mean)


WGS84 = Geodesic.WGS84


class ReceiverSite:
    FilterConstraints = namedtuple("FilterConstraints", ["min", "max"], defaults=[None, None])

    def __init__(self, name, rxPosition, groundConstraints, slantConstraints,
                 verticalConstraints):
        self.nameRx = name
        self.rxPos = rxPosition
        self.ground = groundConstraints
        self.slant = slantConstraints
        self.vertical = verticalConstraints

    def __repr__(self):
        state = {
            'name': self.nameRx,
            'rxLocation': self.rxPos,
            'ground': self.ground,
            'slant': self.slant,
            'vertical': self.vertical
        }
        return pformat(state, indent=4, width=1)

    def getConstraints(self):
        constraints = {
            'ground': self.ground,
            'slant': self.slant,
            'vertical': self.vertical
        }
        return constraints

    def setGroundConstraints(self, constraints):
        if not isinstance(constraints, ReceiverSite.FilterConstraints):
            logging.error("Must give FilterConstraints namedtuple")
        else:
            self.ground = constraints

    def setSlantConstraints(self, constraints):
        if not isinstance(constraints, ReceiverSite.FilterConstraints):
            logging.error("Must give FilterConstraints namedtuple")
        else:
            self.slant = constraints

    def setVerticalConstraints(self, constraints):
        if not isinstance(constraints, ReceiverSite.FilterConstraints):
            logging.error("Must give FilterConstraints namedtuple")
        else:
            self.vertical = constraints

    @staticmethod
    def _haversineDistanceNM(lat1, lon1, lat2, lon2):
        """ Distance between two WGS84 coordinates in nautical miles.
            lat/lon is given in decimal degrees
        """
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        # Haversine formula
        a = (math.sin(dphi / 2) ** 2 +
             math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        d_km = R_km * c  # Distance in km

        d_nm = d_km / KM_PER_NM
        return d_nm

    @staticmethod
    def _geodesicDistanceNM(lat1, lon1, lat2, lon2):
        ''' High-precision ellipsoidal distance in nautical miles
        '''
        result = WGS84.Inverse(lat1, lon1, lat2, lon2)
        meters = result["s12"]
        return meters / METER_PER_NM

    @staticmethod
    def _withinConstraints(value, constraints):
        if constraints.min is not None and value < constraints.min:
            return False
        if constraints.max is not None and value > constraints.max:
            return False
        return True

    def slantDistanceNM(self, lat, lon, alt):
        altNM = alt / FEET_PER_NM
        return math.sqrt((self.groundDistanceNM(lat, lon) ** 2) + (altNM ** 2))

    def groundDistanceNM(self, lat, lon):
        return ReceiverSite._geodesicDistanceNM(self.rxPos.latitude, self.rxPos.longitude, lat, lon)

    def surfaceDistanceToTarget(self, target):
        return ReceiverSite._geodesicDistanceNM(self.rxPos.latitude, self.rxPos.longitude,
                                                target.lat, target.lon)

    def withinTrackingVolume(self, target):
        ''' ?
            ground (min_nm, max_nm)
            slant (min_nm, max_nm)
            altitude (min_ft, max_ft)
        '''
        lat1, lon1, alt1 = self.rxPos
        lat2, lon2, alt2 = target

        groundDistNM = ReceiverSite._geodesicDistanceNM(lat1, lon1, lat2, lon2)

        verticalDistFt = abs(alt2 - alt1)
        verticalDistNM = verticalDistFt / FEET_PER_NM

        slantDistNM = math.sqrt(groundDistNM**2 + verticalDistNM**2)

        if self.ground is not None:
            if not ReceiverSite._withinConstraints(groundDistNM, self.ground):
                return False
        if self.slant is not None:
            if not ReceiverSite._withinConstraints(slantDistNM, self.slant):
                return False
        if self.vertical is not None:
            if not ReceiverSite._withinConstraints(verticalDistFt, self.vertical):
                return False
        return True