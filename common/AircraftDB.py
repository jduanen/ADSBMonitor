#!/usr/bin/python3
#
# Object that encapsulates the mapping between ICAO hex code and Tail Number,
#  aircraft type, and aircraft code
#
# Format of Aircraft DB file lines:
#   <hexCode>,<tailNumber>,<aircraftType>,<aircraftCode>
# ICAO Aircraft Type: ?where defined?
# Aircraft Category Code: <aircraftClassCode><numberOfEngines><typeOfEngine>
#  * aircraftClassCode:
#    - A: Amphibian
#    - G: Gyro
#    - H: Helicopter
#    - L: Landplane
#    - S: Seaplane
#  * numberOfEngines: [1-64]
#  * typeOfEngine:
#    - E: ?Electric?
#    - J: Jet
#    - P: Piston
#    - T: Turbine


import csv


class AircraftDB:
    def __init__(self, dbFilePath):
        try:
            self.filePath = dbFilePath
            self.db = {}
            with open(self.filePath, 'r', encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if row:
                        key = row[0]
                        self.db[key] = row
        except Exception as e:
            logging.error("Failed to load database CSV file '%s': %s", self.filePath, e)


    def getMappings(self, hexCode):
        return self.db.get(hexCode.upper(), ('', '', '', ''))

    def hexCodeToTailNumber(self, hexCode):
        tailNumber = None
        if hexCode.upper() in self.db:
            tailNumber = self.db[hexCode.upper()][1]
        return tailNumber

    def hexCodeToAircraftType(self, hexCode):
        aircraftType = None
        if hexCode.upper() in self.db:
            aircraftType = self.db[hexCode.upper()][2]
        return aircraftType

    def hexCodeToAircraftCode(self, hexCode):
        aircraftCode = None
        if hexCode.upper() in self.db:
            aircraftCode = self.db[hexCode.upper()][3]
        return aircraftCode

    def getAircraftClassCode(self, hexCode):
        code = self.hexCodeToAircraftCode(hexCode)
        if code:
            return code[0]
        return code

    def getNumberOfEngines(self, hexCode):
        code = self.hexCodeToAircraftCode(hexCode)
        if code:
            return int(code[1:-1])
        return code

    def getTypeOfEngines(self, hexCode):
        code = self.hexCodeToAircraftCode(hexCode)
        if code:
            return code[-1]
        return code
