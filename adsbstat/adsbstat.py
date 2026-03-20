#!/usr/bin/env python3
#
# Script that monitors the dump1090-fa program, and gathers stats on the number
#  and type of aircraft near a given position
#
# N.B. options precedence order: cmd line -> conf file -> defaults
#

import argparse
from collections import namedtuple
import json
import logging
import os
from pathlib import Path
from pprint import pprint
import signal
import sys
import threading
import time
import yaml

from watchdog.observers.polling import PollingObserver

ADSB_STAT_VERSION_MAJOR = 0
ADSB_STAT_VERSION_MINOR = 1
ADSB_STAT_VERSION_PATCH = 0
ADSB_STAT_VERSION = f"{ADSB_STAT_VERSION_MAJOR}.{ADSB_STAT_VERSION_MINOR}.{ADSB_STAT_VERSION_PATCH}"

Position = namedtuple("Position", ["latitude", "longitude", "altitude"], defaults=[None, None, None])
FilterConstraints = namedtuple("FilterConstraints", ["min", "max"], defaults=[None, None])

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.JsonFileHandler import JsonFileHandler
from common.AircraftDB import AircraftDB
from common.ReceiverSite import ReceiverSite
from common.Tracks import Tracks

import pdb  ## pdb.set_trace()


STALE_TRACK_TIME = 58  # garbage collect records after 58secs

FILE_UNCHANGED_TIMEOUT = 90  # throw exception if aircraft file doesn't change in 90 secs

ADDITIONAL_FIELDS = True

AIRCRAFT_JSON_FILE = "aircraft.json"

DEFAULTS = {
    'altitude': FilterConstraints(),
    'distance': FilterConstraints(),
    'logFile': None,
    'logLevel': "WARNING",
    'name': "Home",
    'slant': FilterConstraints(),
    'verbose': 0
}


class ExitGracefully:
    def __init__(self, stopEvent):
        ''' Register signals that can cause an exit
        '''
        self.stopEvent = stopEvent
        signal.signal(signal.SIGINT, self._signalHandler)   # Ctl-C
        signal.signal(signal.SIGTERM, self._signalHandler)  # kill command
        signal.signal(signal.SIGHUP, self._signalHandler)   # terminal closed

    def _signalHandler(self, sig, frame):
        ''' Catch SIGHUP to force a restart and SIGINT to stop
        '''
        match sig:
            case signal.SIGHUP:
                logging.info("SIGHUP: stopping")
                self.stopEvent.set()
            case signal.SIGINT:
                logging.info("SIGINT: stopping")
                self.stopEvent.set()
            case _:
                logging.info("unknown signal: %s", sig)


def getOpts():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-a", "--altitude", metavar=["min", "max"], type=float,
        help="Min/max vertical difference filter constraint (from receiver in Feet)")
    ap.add_argument(
        "-c", "--configFilePath", action="store", type=str,
        help="Path to the configuration YAML file")
    ap.add_argument(
        "-D", "--distance", metavar=["min", "max"], type=float,
        help="Min/max surface distance filter constraint (from receiver in NM)")
    ap.add_argument(
        "-d", "--dbFilePath", action="store", type=str,
        help="Path to the plane database")
    ap.add_argument(
        "-L", "--logLevel", action="store", type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level")
    ap.add_argument(
        "-l", "--logFile", action="store", type=str,
        help="Path to the logfile (create it if it doesn't exist)")
    ap.add_argument(
        "-n", "--name", action="store", type=str,
        help="Name of the receiver site")
    ap.add_argument(
        "-p", "--position", metavar=("lat", "lon", "alt"), type=float, nargs=3,
        help="Position: <lat> <lon> <alt>")
    ap.add_argument(
        "-s", "--slant", metavar=["min", "max"], type=float,
        help="Min/max slant distance filter constraint (from receiver in NM)")
    ap.add_argument(
        "-v", "--verbose", action="count",
        help="Print debug info")
    ap.add_argument("adsbPath",
        help="Path to where the dump1090-fa program stores its data")
    cliOpts = ap.parse_args().__dict__

    # cliOpts=cmd line options; fileOpts=conf file options; DEFAULT=default options
    configFilePath = None
    conf = {'version': ADSB_STAT_VERSION, 'cliOpts': cliOpts, 'fileOpts': {},
            'config': {}, 'defaults': DEFAULTS}
    if conf['cliOpts']['configFilePath']:
        configFilePath = cliOpts['configFilePath']
    else:
        configFilePath = DEFAULTS.get('configFilePath', None)
    if configFilePath:
        if not os.path.exists(configFilePath):
            print(f"ERROR: Invalid configuration file path: {configFilePath}", file=sys.stderr)
            sys.exit(1)
        with open(configFilePath, "r", encoding="utf-8") as confFile:
            fileOpts = list(yaml.load_all(confFile, Loader=yaml.Loader))
            if len(fileOpts) >= 1:
                conf['fileOpts'] = fileOpts[0]
                if len(fileOpts) > 1:
                    print("WARNING: Multiple config docs. Using the first one",
                          file=sys.stderr)

    c = conf['config']
    for opt in [action.dest for action in ap._actions if action.dest != 'help']:
        if opt in conf['cliOpts'] and conf['cliOpts'][opt] is not None:
            c[opt] = conf['cliOpts'][opt]
        elif opt in conf['fileOpts'] and conf['fileOpts'][opt] is not None:
            c[opt] = conf['fileOpts'][opt]
        elif opt in conf['defaults'] and conf['defaults'][opt] is not None:
            c[opt] = conf['defaults'][opt]
        else:
            c[opt] = None
    if c['verbose'] > 1:
        json.dump(conf, sys.stdout, indent=4, sort_keys=True)
        print("")

    if c['logFile']:
        logging.basicConfig(filename=c['logFile'], level=c['logLevel'])
    else:
        logging.basicConfig(level=c['logLevel'])

    if all(c['distance']) and c['distance'].min  >= c['distance'].max:
        logging.error("Invalid constraint: ground distance min %f >= max %f NM",
                      c['distance'][0], c['distance'][1])
        sys.exit(1)
    if all(c['slant']) and c['slant'].min  >= c['slant'].max:
        logging.error("Invalid constraint: slant distance min %f >= max %f NM",
                      c['slant'][0], c['slant'][1])
        sys.exit(1)
    if all(c['altitude']) and c['altitude'].min  >= c['altitude'].max:
        logging.error("Invalid constraint: vertical distance min %f >= max %f NM",
                      c['altitude'][0], c['altitude'][1])
        sys.exit(1)

    if 'adsbPath' not in c:
        logging.error("Must specify the path to where dump1090-fa stores its files")
        sys.exit(1)
    return c


def run(options):
    def usr1Handler(sig, frame):
        tracksObj.printAll()
    signal.signal(signal.SIGUSR1, usr1Handler)   # 'kill -USR1' to print current tracks

    stopEvent = threading.Event()
    ExitGracefully(stopEvent)

    if options['verbose'] > 1:
        json.dump(options, sys.stdout, indent=4, sort_keys=True)
        print("")

    aircraftDbObj = AircraftDB(options['dbFilePath'])

    homePosition = Position(options['position'][0], options['position'][1],
                            options['position'][2])
    groundConstriants = FilterConstraints(options['distance'][0], options['distance'][1])
    slantConstriants = FilterConstraints(options['slant'][0], options['slant'][1])
    verticalConstriants = FilterConstraints(options['altitude'][0], options['altitude'][1])
    rxSiteObj = ReceiverSite(options['name'], homePosition, slantConstriants,
                             groundConstriants, verticalConstriants)
    if options['verbose'] > 1:
        repr(rxSiteObj)

    def createStaleTrackHandler(aircraftDatabase, receiverSite, mqttClient):
        ''' Returns a closure that captures instances of AircraftDB and ReceiverSite
             for use in dealing with a stale track that is to be garbage collected
        '''
        def staleTrack(staleHexId, currentTracks):
            ''' Called whenever a stale track is to be deleted
                N.B. This is called before the track is deleted
            '''
            acDB = aircraftDatabase
            rx = receiverSite
            mC = mqttClient

            print(f"stale Track: {staleHexId} #{len(currentTracks)}")  #### TMP TMP TMP
        return staleTrack
    staleTrackHandler = createStaleTrackHandler(aircraftDbObj, rxSiteObj, mqttClient)

    tracksObj = Tracks(aircraftDbObj, rxSiteObj, STALE_TRACK_TIME, staleTrackHandler)

    def createAddedMessageHandler(aircraftDatabase, receiverSite, mqttClient):
        ''' Returns a closure that captures instances of AircraftDB and ReceiverSite
             for use in dealing with a new ADS-B message
        '''
        def addedMessage(newHexId, currentTracks):
            ''' This is called whenever a new ADS-B message is added to a track
                N.B. This is called after the message has been added to its Track
            '''
            acDB = aircraftDatabase
            rx = receiverSite

            msg = currentTracks[newHexId][-1]['msg']
            if not {'lat', 'lon'} <= msg.keys():
                return

            if len(currentTracks[newHexId]) <= 1:
                trackName = currentTracks[newHexId][-1]['msg'].get('flight', newHexId)
                print(f"new Track: {newHexId} {trackName} ", end="")

            planeInfo = acDB.getMappings(newHexId)
            currentTracks[newHexId][-1]['msg']['acType'] = planeInfo[2]
            currentTracks[newHexId][-1]['msg']['acDesc'] = planeInfo[3]

            numTracks = len(currentTracks)
            print(f"# {numTracks}")
        return addedMessage
    addedMessageHandler = createAddedMessageHandler(aircraftDbObj, rxSiteObj, mqttClient)

    dumpDir = Path(options['adsbPath'])

    observer = PollingObserver()
    aircraftJsonPath = dumpDir / AIRCRAFT_JSON_FILE
    handler = JsonFileHandler(aircraftJsonPath, tracksObj, addedMessageHandler)
    observer.schedule(handler, path=str(aircraftJsonPath), recursive=False)
    observer.start()
    logging.debug("Watching %s...", str(aircraftJsonPath))
    try:
        while observer.is_alive() and not stopEvent.is_set():
            time.sleep(1.0)  # 1sec poll
            if time.time() - handler.lastChanged > FILE_UNCHANGED_TIMEOUT:
                logging.error("No update of %s for %s secs",
                              aircraftJsonPath, FILE_UNCHANGED_TIMEOUT)
                break
            if stopEvent.wait(0.1):  # non-blocking check
                break
    finally:
        observer.stop()
        observer.join()
    logging.debug("Observer exited")

    tracksObj.removeAllTracks()
    tracksObj.stopGarbageCollect()
    logging.debug("Shutdown complete, exiting")
    sys.exit(0)


if __name__ == "__main__":
    opts = getOpts()
    run(opts)


'''
            if {'lat', 'lon'} <= msg.keys():
                distance = self.rxSite.distance2dNM(msg['lat'], msg['lon'])
                logging.debug("distance: %f", distance)
                if distance <= self.rxSite.max2dDistance:
                    requiredKeys = {'alt_geom', 'category', 'gs', 'hex', 'seen_pos'}
                    missingKeys = requiredKeys  - msg.keys()
                    if missingKeys:
                        logging.error("Message is missing fields: %s", missingKeys)
                        continue

                    additionalKeys = {'baro_rate', 'emergency', 'flight', 'geom_rate', 'rssi', 'seen'}
                    hexId = msg['hex']
                    mappings = self.aircraftDB.getMappings(hexId)
                    if not mappings[0]:
                        logging.error("HexId '%s' not found in AircraftDB", hexId)
                        continue
                    record = {
                        'acType': mappings[2],
                        'acCode': mappings[3],
                        'dist2d': distance,
                        'dist3d': self.rxSite.distance3dNM(msg['lat'], msg['lon'], msg['alt_geom']),
                        'ts': data['now'],
                        'tn': mappings[1]
                    }
                    requiredFields = {k: msg.get(k) for k in requiredKeys}
                    record.update(requiredFields)
                    if ADDITIONAL_FIELDS:
                        addedFields = {k: msg.get(k) for k in additionalKeys}
                        record.update(addedFields)

                    if hexId in self.records:
                        self.records[hexId].append(record)
                    else:
                        self.records[hexId] = [record]
                    #### TMP TMP TMP
                    for h, l in self.records.items():
                        lastSeen = l[-1]['ts'] + l[-1]['seen_pos']
                        print(f"> {h}: {len(l)}, {datetime.fromtimestamp(lastSeen)}")
                    print("")

                    # GC the track records
                    for hexId, recordList in self.records.items():
                        lastSeen = l[-1]['ts'] + l[-1]['seen_pos']
                        now = time.time()
                        print(f"{l[-1]['ts']}, {l[-1]['seen_pos']}, {now}")
                        if now > lastSeen + STALE_TRACK_TIME:
                            print(f"GC: {hexId}")
                            del(self.records[hexId])
'''
