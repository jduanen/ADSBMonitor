#!/usr/bin/env python3
#
# Script that monitors the dump1090-fa program, maintains tracks of currently
#  visible crafts, and emits MQTT messages that contain track updates.
#
# N.B. options precedence order: cmd line -> conf file -> defaults
#

import argparse
from collections import namedtuple
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import signal
import sys
import threading
import time
import yaml

from watchdog.observers.polling import PollingObserver

ADSB_MON_VERSION_MAJOR = 1
ADSB_MON_VERSION_MINOR = 0
ADSB_MON_VERSION_PATCH = 0
ADSB_MON_VERSION = f"{ADSB_MON_VERSION_MAJOR}.{ADSB_MON_VERSION_MINOR}.{ADSB_MON_VERSION_PATCH}"

Position = namedtuple("Position", ["latitude", "longitude", "altitude"], defaults=[None, None, None])

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from AdsbMqtt import AdsbMqtt
from common.AircraftDB import AircraftDB
from common.JsonFileHandler import JsonFileHandler
from common.ReceiverSite import ReceiverSite, FilterConstraints
from common.RouteDB import RouteDB
from common.Tracks import Tracks


STALE_TRACK_TIME = 28  # garbage collect records after this many secs

FILE_UNCHANGED_TIMEOUT = 90  # throw exception if aircraft file doesn't change in 90 secs

AIRCRAFT_JSON_FILE = "aircraft.json"

MQTT_CLIENT_ID = "adsb_vehicles"

DEFAULTS = {
    'altitude': FilterConstraints(),
    'groundDistance': FilterConstraints(),
    'logFile': None,
    'logLevel': "WARNING",
    'mqttHost': "homeassistant.lan",
    'mqttPort': 1883,
    'mqttUsername': None,
    'mqttPasswd': None,
    'mqttKeepalive': 60,  # 1min
    'name': "Home",
    #'readHistory': False,
    'slantDistance': FilterConstraints(),
    'verbose': None
}

EMPTY_MSG = {'track_name': '---', 's_dist': '---', 'g_dist': '---',
             'alt': '---', 'ac_type': '---', 'hex': '---',
             'origin_iata': '---', 'origin_icao': '----','origin_code': '--- (----)', 'origin_name': '', 'origin_abbr': '',
             'dest_iata': '---', 'dest_icao': '----','dest_code': '--- (----)', 'dest_name': '', 'dest_abbr': ''}


class ExitGracefully:
    def __init__(self, stopEvent):
        ''' Register signals that can cause an exit
        '''
        self.stopEvent = stopEvent
        signal.signal(signal.SIGINT, self._signalHandler)   # Ctl-C
        signal.signal(signal.SIGTERM, self._signalHandler)  # kill command
        signal.signal(signal.SIGHUP, self._signalHandler)   # terminal closed

    def _signalHandler(self, sig, frame):
        ''' Signals set the stop event (which should cause a cleanup and exit)
        '''
        match sig:
            case signal.SIGHUP:
                logging.info("SIGHUP: stopping")
            case signal.SIGINT:
                logging.info("SIGINT: stopping")
            case signal.SIGTERM:
                logging.info("SIGTERM: stopping")
            case _:
                logging.info("unknown signal: %s", sig)
                return
        self.stopEvent.set()


def getOpts():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-a", "--altitude", metavar=["min", "max"], type=int, nargs=2,
        help="Min/max vertical distance filter constraint (from receiver in Feet)")
    ap.add_argument(
        "-b", "--mqttHost", action="store", type=str,
        help="Path to the MQTT broker")
    ap.add_argument(
        "-c", "--configFilePath", action="store", type=str,
        help="Path to the configuration YAML file")
    ap.add_argument(
        "-g", "--groundDistance", metavar=["min", "max"], type=float, nargs=2,
        help="Min/max surface distance filter constraint (from receiver in NM)")
    ap.add_argument(
        "-d", "--dbFilePath", action="store", type=str,
        help="Path to the plane database")
    ap.add_argument(
        "-k", "--mqttKeepalive", action="store", type=int,
        help="MQTT connection keep alive time (secs)")
    ap.add_argument(
        "-L", "--logLevel", action="store", type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level")
    ap.add_argument(
        "-l", "--logFile", action="store", type=str,
        help="Path to the logfile (create it if it doesn't exist)")
    ap.add_argument(
        "-m", "--mqttPort", action="store", type=int,
        help="MQTT Broker port number")
    ap.add_argument(
        "-n", "--name", action="store", type=str,
        help="Name of the receiver site")
    ap.add_argument(
        "-P", "--mqttPasswd", action="store", type=str,
        help="MQTT password")
    ap.add_argument(
        "-p", "--position", metavar=("lat", "lon", "alt"), type=float, nargs=3,
        help="Position: <lat> <lon> <alt>")
    #ap.add_argument(
    #    "-r", "--readHistory", action="store_true",
    #    help="Read history files on startup")
    ap.add_argument(
        "-s", "--slantDistance", metavar=["min", "max"], type=float, nargs=2,
        help="Min/max slant distance filter constraint (from receiver in NM)")
    ap.add_argument(
        "-u", "--mqttUsername", action="store", type=str,
        help="MQTT user name")
    ap.add_argument(
        "-v", "--verbose", action="count",
        help="Print debug info")
    ap.add_argument("adsbPath",
        help="Path to where the dump1090-fa program stores its data")
    cliOpts = ap.parse_args().__dict__

    # cliOpts=cmd line options; fileOpts=conf file options; DEFAULT=default options
    configFilePath = None
    conf = {'version': ADSB_MON_VERSION, 'cliOpts': cliOpts, 'fileOpts': {},
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
            fileOpts = list(yaml.load_all(confFile, Loader=yaml.SafeLoader))
            if len(fileOpts) >= 1:
                conf['fileOpts'] = fileOpts[0] if fileOpts[0] is not None else {}
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
    if (c['verbose'] or 0) > 1:
        json.dump(conf, sys.stdout, indent=4, sort_keys=True)
        print("")

    if c['logFile']:
        logging.basicConfig(filename=c['logFile'], level=c['logLevel'])
    else:
        logging.basicConfig(level=c['logLevel'])

    if not c['position']:
        logging.error("Must give position of receiver")
        sys.exit(1)

    for key in ('groundDistance', 'slantDistance', 'altitude'):
        if isinstance(c[key], list):
            c[key] = FilterConstraints(*c[key])

    if c['groundDistance'].min is not None and c['groundDistance'].max is not None and c['groundDistance'].min >= c['groundDistance'].max:
        logging.error("Invalid constraint: ground distance min %f >= max %f NM",
                      c['groundDistance'][0], c['groundDistance'][1])
        sys.exit(1)
    if c['slantDistance'].min is not None and c['slantDistance'].max is not None and c['slantDistance'].min  >= c['slantDistance'].max:
        logging.error("Invalid constraint: slant distance min %f >= max %f NM",
                      c['slantDistance'][0], c['slantDistance'][1])
        sys.exit(1)
    if c['altitude'].min is not None and c['altitude'].max is not None and c['altitude'].min  >= c['altitude'].max:
        logging.error("Invalid constraint: altitude/vertical distance min %f >= max %f NM",
                      c['altitude'][0], c['altitude'][1])
        sys.exit(1)

    if not c['dbFilePath'] or not Path(c['dbFilePath']).is_file():
        logging.error("Must provide valid path to the AircraftDB")
        sys.exit(1)

    if not Path(c['adsbPath']).is_dir():
        logging.error("adsbPath does not exist or is not a directory: %s", c['adsbPath'])
        sys.exit(1)
    return c


def run(options):
    def usr1Handler(sig, frame):
        tracksObj.printAll()

    stopEvent = threading.Event()
    _exit = ExitGracefully(stopEvent)

    if (options['verbose'] or 0) > 1:
        json.dump(options, sys.stdout, indent=4, sort_keys=True)
        print("")

    aircraftDbObj = AircraftDB(options['dbFilePath'])

    rxSiteObj = ReceiverSite(options['name'], Position(*options['position']),
                             options['groundDistance'],
                             options['slantDistance'],
                             options['altitude'])
    logging.info(repr(rxSiteObj))

    try:
        mqttClient = AdsbMqtt(MQTT_CLIENT_ID,
                              options['mqttHost'], options['mqttPort'],
                              options['mqttKeepalive'], options['mqttUsername'],
                              options['mqttPasswd'])
    except (ConnectionError, RuntimeError) as e:
        logging.error("MQTT setup failed: %s", e)
        sys.exit(1)

    def createStaleTrackHandler(mqttClient):
        ''' Returns a closure that captures the mqttClient instance for use in
             dealing with a stale track that is to be garbage collected
        '''
        def staleTrack(staleHexId):
            ''' Called whenever a stale track that was being tracked is to be deleted
                This is unnecessary, but I might want to add other stuff later
            '''
            mqttClient.publishNullTrackDiscoveryMsg(staleHexId)
        return staleTrack

    staleTrackHandler = createStaleTrackHandler(mqttClient)

    tracksObj = Tracks(aircraftDbObj, rxSiteObj, STALE_TRACK_TIME, staleTrackHandler)

    mqttClient.publishServiceDiscoveryMsg()
    mqttClient.publishTracksCountDiscoveryMsg()
    mqttClient.publishInVolumeCountDiscoveryMsg()
    for rank in range(1, 4):
        mqttClient.publishNearestDiscoveryMsg(rank)
    logging.info("Published Service, TracksCount, InVolumeCount, and Nearest discovery messages")

    def createNewMessagesHandler(aircraftDatabase, rxObj, trksObj, mqttClient, routeDb):
        ''' Returns a closure that captures instances of objects needed by the callback
             for use in dealing with new ADS-B messages
        '''
        def newMessages(data):
            ''' Function that gets called each time a new list of messages is
                 written to the log file.
            '''
            def abbreviate(airportName):
                abbr = re.sub(r'International|Airport|airport',
                              lambda m: 'Intl' if m.group() in ('International', 'international') else '',
                              airportName)
                return abbr

            try:
                msgTime = data['now']
                for msg in data['aircraft']:
                    if 'hex' not in msg:
                        logging.warning("Malformed message, no 'hex' field, skipping message")
                        continue
                    if not {'lat', 'lon'} <= msg.keys():
                        logging.debug("Message is missing lat or lon, skipping (%s)", msg['hex'])
                        continue
                    if msg.get('alt_geom') is not None:
                        alt = msg['alt_geom']
                    elif msg.get('alt_baro') is not None:
                        alt = msg['alt_baro']
                    else:
                        logging.debug("Message is missing altitude field, skipping (%s)", msg['hex'])
                        continue
                    alt = 0 if alt == 'ground' else alt
                    msg['alt'] = alt

                    if msg['hex'].startswith('~'):
                        msg['hex'] = '_' + msg['hex'][1:]

                    msg['g_dist'] = round(rxObj.groundDistanceNM(msg['lat'], msg['lon']), 4)
                    msg['s_dist'] = round(rxObj.slantDistanceNM(msg['lat'], msg['lon'], alt), 4)

                    trackPosition = Position(msg['lat'], msg['lon'], alt)
                    inVolume = rxObj.withinTrackingVolume(trackPosition)
                    logging.debug("Track %s @ %s: inVolume=%s", msg['hex'], trackPosition, inVolume)

                    planeInfo = aircraftDatabase.getMappings(msg['hex'])
                    msg['ac_type'] = planeInfo[2] if planeInfo[2] else "_"
                    msg['ac_desc'] = planeInfo[3] if planeInfo[3] else "_"
                    trackName = msg.get('flight', msg['hex']).strip()
                    msg['track_name'] = trackName

                    callsign = msg.get('flight', '').strip()
                    route = routeDb.getRoute(callsign) if callsign else None
                    logging.debug(f"route: {route}")
                    if route:
                        msg['origin_iata'] = route['origin_iata']
                        msg['origin_icao'] = route['origin_icao']
                        msg['origin_code'] = f"{route['origin_iata']} ({route['origin_icao']})"
                        msg['origin_name'] = route['origin_name']
                        msg['origin_abbr'] = abbreviate(route['origin_name'])

                        msg['dest_iata'] = route['dest_iata']
                        msg['dest_icao'] = route['dest_icao']
                        msg['dest_code'] = f"{route['dest_iata']} ({route['dest_icao']})"
                        msg['dest_name'] = route['dest_name']
                        msg['dest_abbr'] = abbreviate(route['dest_name'])
                    else:
                        msg['origin_iata'] = '---'
                        msg['origin_icao'] = '----'
                        msg['origin_code'] = '---' ('----')
                        msg['origin_name'] = ''
                        msg['origin_abbr'] = ''

                        msg['dest_iata'] = '---'
                        msg['dest_icao'] = '----'
                        msg['dest_code'] = '---' ('----')
                        msg['dest_name'] = ''
                        msg['dest_abbr'] = ''

                    if inVolume:
                        if not trksObj.isInVolume(msg['hex']):
                            logging.debug("%s (%s) was not in volume before this", trackName, msg['hex'])
                            mqttClient.publishTrackDiscoveryMsg(msg['hex'], trackName)
                            # delay to allow HA discovery to take place before updating
                            threading.Timer(0.1, mqttClient.publishTrackUpdateMsg, args=[msg['hex'], dict(msg)]).start()
                        else:
                            mqttClient.publishTrackUpdateMsg(msg['hex'], msg)
                        trksObj.updateTrack(inVolume, msgTime, msg)
                    else:
                        logging.debug("%s not in volume", msg['hex'])
                        if trksObj.isInVolume(msg['hex']):
                            logging.debug("%s was in volume before this, and now it's not", msg['hex'])
                            trksObj.removeTrack(msg['hex'])  # staleHandler will send the null state update
                        else:
                            trksObj.updateTrack(inVolume, msgTime, msg)

                mqttClient.publishInVolumeCountUpdateMsg(len(trksObj.inVolumeTrackIds()))
                mqttClient.publishTracksCountUpdateMsg(trksObj.numberOfTracks())
                _nearest = sorted(trksObj.getInVolumeTracks(),
                                  key=lambda m: m.get('s_dist', float('inf')))
                _empty = EMPTY_MSG
                for _rank in range(1, 4):
                    _data = _nearest[_rank - 1] if _rank <= len(_nearest) else _empty
                    mqttClient.publishNearestUpdateMsg(_rank, _data)
            except Exception:
                logging.exception("Exception in newMessages")
        return newMessages

    routeDbObj = RouteDB()
    newMessagesHandler = createNewMessagesHandler(aircraftDbObj, rxSiteObj, tracksObj, mqttClient, routeDbObj)

    dumpDir = Path(options['adsbPath'])

    signal.signal(signal.SIGUSR1, usr1Handler)   # 'kill -USR1' to print current tracks

    #### FIXME decide to implement this or not
    '''
-    if options['readHistory']:
-        historyFiles = sorted(dumpDir.glob("history_*.json"),
-                              key=lambda p: p.stat().st_mtime)
-        for path in historyFiles:
-            try:
-                data = json.loads(path.read_text('utf-8'))
-                ts = datetime.fromtimestamp(data['now'])
-                logging.info(f"read history file {path.name}; now={ts}; {len(data['aircraft'])} msgs")
-                #### TODO put data integrity checks here -- data.now, data.messages, data.aircraft[]
-                for msg in data['aircraft']:
-                    processMsg(msg['hex'], msg, data['now'])
-            except json.JSONDecodeError:
-                logging.warning(f"Invalid JSON in: {path}")
-            except UnicodeDecodeError:
-                logging.warning(f"Can't read: {path}")
    '''

    mqttClient.publishServiceStateMsg(True)
    logging.info("Published Service state True @ %s", datetime.now())

    observer = PollingObserver()
    aircraftJsonPath = dumpDir / AIRCRAFT_JSON_FILE
    handler = JsonFileHandler(aircraftJsonPath, newMessagesHandler)
    observer.schedule(handler, path=str(dumpDir), recursive=False)
    observer.start()
    logging.debug("Watching %s...", str(aircraftJsonPath))
    try:
        while observer.is_alive() and not stopEvent.is_set():
            if stopEvent.wait(1.0):
                break
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
    mqttClient.publishTracksCountUpdateMsg(0)
    mqttClient.publishInVolumeCountUpdateMsg(0)
    _empty = EMPTY_MSG
    for rank in range(1, 4):
        mqttClient.publishNearestUpdateMsg(rank, _empty)
    info = mqttClient.publishServiceStateMsg(False)
    logging.info("Published zero to Tracks and InVolume counts and Service state False @ %s",
                 datetime.now())
    try:
        info.wait_for_publish(timeout=5.0)
    except (ValueError, RuntimeError) as e:
        logging.warning("MQTT flush failed: %s", e)
    tracksObj.stopGarbageCollect()
    logging.debug("Shutdown complete, exiting")


if __name__ == "__main__":
    opts = getOpts()
    run(opts)
