#!/usr/bin/env python3
#
# Script that monitors the dump1090-fa program, maintains tracks of currently
#  visible crafts, and emits MQTT messages that contain track updates.
#
# N.B. options precedence order: cmd line -> conf file -> defaults
#
# MQTT publish topics:
#  * publishServiceDiscoveryMsg:          "homeassistant/binary_sensor/adsb_monitor/status/config"
#  * publishServiceStateMsg:              "adsb/monitor/status"
#  * publishTrackDiscoveryMsg:            f"homeassistant/sensor/adsb_{message['hex']}/config"
#  * publishNullTrackDiscoveryMsg:        f"homeassistant/sensor/adsb_{message['hex']}/config"
#  * publishTrackUpdateMsg:               f"adsb/vehicles/{message['hex']}/state"
#  * publishTracksCountDiscoveryMsg:      "homeassistant/sensor/adsb_monitor/count/config"
#  * publishNullTracksCountDiscoveryMsg:  "homeassistant/sensor/adsb_monitor/count/config"
#  * publishTracksCountUpdateMsg:         "adsb/monitor/count"
#

import argparse
from datetime import datetime
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

ADSB_MON_VERSION_MAJOR = 0
ADSB_MON_VERSION_MINOR = 2
ADSB_MON_VERSION_PATCH = 0
ADSB_MON_VERSION = f"{ADSB_MON_VERSION_MAJOR}.{ADSB_MON_VERSION_MINOR}.{ADSB_MON_VERSION_PATCH}"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from AdsbMqtt import AdsbMqtt
from common.JsonFileHandler import JsonFileHandler
from common.AircraftDB import AircraftDB
from common.ReceiverSite import ReceiverSite
from common.Tracks import Tracks

import pdb  ## pdb.set_trace()


STALE_TRACK_TIME = 58  # garbage collect records after 58secs

FILE_UNCHANGED_TIMEOUT = 90  # throw exception if aircraft file doesn't change in 90 secs

ADDITIONAL_FIELDS = True

AIRCRAFT_JSON_FILE = "aircraft.json"

MQTT_CLIENT_ID = "adsb_vehicles"

DEFAULTS = {
    'logFile': None,
    'logLevel': "WARNING",
    'maxDistance': None,
    'name': "Home",
    'readHistory': False,
    'mqttHost': "homeassitant.lan",
    'mqttPort': 1883,
    'mqttUsername': None,
    'mqttPasswd': None,
    'mqttKeepalive': 60,  # 1min
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
        "-b", "--mqttHost", action="store", type=str,
        help="Path to the configuration file")
    ap.add_argument(
        "-c", "--configFilePath", action="store", type=str,
        help="Path to the configuration YAML file")
    ap.add_argument(
        "-D", "--maxDistance", action="store", type=float,
        help="Max distance from receiver in NM")
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
    ap.add_argument(
        "-r", "--readHistory", action="store_true", default=False,
        help="Read history files on startup")
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

    rxSiteObj = ReceiverSite(options['name'], options['maxDistance'],
                             options['position'][0], options['position'][1],
                             options['position'][2])
    if options['verbose'] > 1:
        rxSiteObj.print()

    mqttClient = AdsbMqtt(MQTT_CLIENT_ID,
                          options['mqttHost'], options['mqttPort'],
                          options['mqttKeepalive'], options['mqttUsername'],
                          options['mqttPasswd'])
    if not mqttClient:
        sys.exit(1)

    def createStaleTrackHandler(aircraftDatabase, receiverSite, mqttClient, maxDistance=None):
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
            maxDist = maxDistance
            print(f"stale Track: {staleHexId} #{currentTracks.numberOfTracks()}")  #### TMP TMP TMP
        return staleTrack
    staleTrackHandler = createStaleTrackHandler(aircraftDbObj, rxSiteObj, mqttClient, options['maxDistance'])

    tracksObj = Tracks(aircraftDbObj, rxSiteObj, STALE_TRACK_TIME, staleTrackHandler)

    mqttClient.publishServiceDiscoveryMsg()
    mqttClient.publishTracksCountDiscoveryMsg()
    logging.info("Published Service and Tracks Count discovery messages")

    def createAddedMessageHandler(aircraftDatabase, receiverSite, mqttClient, maxDistance=None):
        ''' Returns a closure that captures instances of AircraftDB and ReceiverSite
             for use in dealing with a new ADS-B message
        '''
        def addedMessage(newHexId, currentTracks):
            ''' This is called whenever a new ADS-B message is added to a track
                N.B. This is called after the message has been added to its Track
            '''
            acDB = aircraftDatabase
            rx = receiverSite
            mC = mqttClient
            maxDist = maxDistance
            print(f"added message: {newHexId} #{len(currentTracks)}")  #### TMP TMP TMP
            msg = currentTracks[newHexId][-1]['msg']
            if not {'lat', 'lon'} <= msg.keys():
                print("Missing position, skipping...")
                return
            lat = msg.lat
            lon = msg.lon
            rDist = msg.r_dst
            print(f"lat={lat}, lon={lon}, rDist={rDist}")
        return addedMessage
    addedMessageHandler = createAddedMessageHandler(aircraftDbObj, rxSiteObj, mqttClient, options['maxDistance'])

    dumpDir = Path(options['adsbPath'])

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
    logging.info("Published Service state True @ %s",
                 datetime.fromtimestamp(time.time()))

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

    mqttClient.publishTracksCountUpdateMsg(0)
    mqttClient.publishServiceStateMsg(False)
    logging.info("Published Tracks Count 0 and Service state False @ %s",
                 datetime.fromtimestamp(time.time()))
    time.sleep(0.6)  # allow mqtt message to be sent before exiting
    tracksObj.stopGarbageCollect()
    logging.debug("Shutdown complete, exiting")
    sys.exit(0)


if __name__ == "__main__":
    opts = getOpts()
    run(opts)
