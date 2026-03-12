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
import signal
import sys
import threading
import time
import yaml

from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

from Track import Track
from MyMqtt import MyMqtt

import pdb  ## pdb.set_trace()


ADSB_MON_VERSION_MAJOR = 0
ADSB_MON_VERSION_MINOR = 1
ADSB_MON_VERSION_PATCH = 0
ADSB_MON_VERSION = f"{ADSB_MON_VERSION_MAJOR}.{ADSB_MON_VERSION_MINOR}.{ADSB_MON_VERSION_PATCH}"

TRACK_STALE_TIME = (60 * 3)  # consider a track stale if no updates in 3mins

GC_RUN_INTERVAL = (60 * 1)   # run the garbage collector every 1mins

AIRCRAFT_JSON_FILE = "aircraft.json"

MQTT_CLIENT_ID = "adsb_vehicles"

DEFAULTS = {
    'logFile': None,
    'logLevel': "WARNING",
    'readHistory': False,
    'mqttHost': "homeassitant.lan",
    'mqttPort': 1883,
    'mqttUsername': None,
    'mqttPasswd': None,
    'mqttKeepalive': 60,  # 1min
    'verbose': 0
}

tracks = {}

stopEvent = None

lock = threading.Lock()

mqttClient = None

debug = False


class JsonHandler(FileSystemEventHandler):
    def __init__(self, filePath):
        self.filePath = filePath

    def on_any_event(self, event):
        if event.src_path.endswith(AIRCRAFT_JSON_FILE) and event.is_directory is False:
            self.readJson()

    def readJson(self):
        numTracks = len(tracks)
        publishTracksCountUpdateMsg(numTracks)
        logging.debug(f"Updated tracks count: {numTracks}")
        try:
            text = self.filePath.read_text(encoding='utf-8')
            data = json.loads(text)
            ts = datetime.fromtimestamp(data['now'])
            logging.info(f"aircraft.json updated @ {datetime.fromtimestamp(time.time())}; data['now']={ts}; # msgs: {len(data['aircraft'])}")
            #### TODO put data integrity checks here -- data.now, data.messages, data.aircraft[]
            for msg in data['aircraft']:
                processMsg(msg['hex'], msg, data['now'])
        except Exception as e:
            logging.error(f"Failed to read {self.filePath}: {e}")


class ExitGracefully:
    def __init__(self):
        ''' Register signals that can cause an exit
        '''
        signal.signal(signal.SIGINT, self._signalHandler)   # Ctl-C
        signal.signal(signal.SIGTERM, self._signalHandler)  # kill command
        signal.signal(signal.SIGHUP, self._signalHandler)   # terminal closed

    def _signalHandler(self, sig, frame):
        ''' Catch SIGHUP to force a restart and SIGINT to stop
        '''
        match sig:
            case signal.SIGHUP:
                logging.info("SIGHUP: stopping")
                stopEvent.set()
            case signal.SIGINT:
                logging.info("SIGINT: stopping")
                stopEvent.set()
            case _:
                logging.info(f"unknown signal: {sig}")


# Service discovery and state update
def publishServiceDiscoveryMsg():
    topic = "homeassistant/binary_sensor/adsb_monitor/status/config"
    msg = {
        "name": "ADS-B Monitor",
        "device_class": "connectivity",
        "state_topic": "adsb/monitor/status",
        "payload_on": "online",
        "payload_off": "offline",
        "unique_id": "adsb_monitor_status",
        "device": {
            "identifiers": ["adsb_monitor"],
            "name": "ADS-B Receiver",
            "manufacturer": "Raspberry Pi 4B",
            "model": "FlightAware USB",
            "sw_version": "bookworm"

        },
        "origin": {
            "name": "adsbmon.py",
            "sw": f"{ADSB_MON_VERSION_MAJOR}.{ADSB_MON_VERSION_MINOR}"
        }
    }
    mqttClient.publishJson(topic, msg, retain=True)


def publishServiceStateMsg(online):
    topic = "adsb/monitor/status"
    msg = "online" if online else "offline"
    mqttClient.publishJson(topic, msg, retain=True)


# Track discovery, null discovery, and update
def publishTrackDiscoveryMsg(hexId):
    topic = f"homeassistant/sensor/adsb_{hexId}/config"
    msg = {
        "name": f"ADS-B Flight {hexId}",
        "unique_id": f"{hexId}",
        "state_topic": f"adsb/vehicles/{hexId}/state",
        "unit_of_measurement": "vehicles",
        "device": {
            "identifiers": [f"adsb_vehicle_{hexId}"],
            "name": f"Vehicle {hexId}",
        },
        "json_attributes_topic": f"adsb/vehicles/state",
        "value_template": "{{ value_json.icao24 }}",
        "device_class": None,
        "state_class": None,
        "origin": {
            "name": "adsbmon.py",
            "sw": f"{ADSB_MON_VERSION_MAJOR}.{ADSB_MON_VERSION_MINOR}"
        }
    }
    mqttClient.publishJson(topic, msg, retain=True)


def publishNullTrackDiscoveryMsg(hexId):
    topic = f"homeassistant/sensor/adsb_{hexId}/config"
    mqttClient.publishJson(topic, "", retain=True)


def publishTrackUpdateMsg(hexId, message):
    topic = f"adsb/vehicles/{hexId}/state"
    mqttClient.publishJson(topic, message)


# Tracks count discovery, null discovery, and update
def publishTracksCountDiscoveryMsg():
    topic = "homeassistant/sensor/adsb_monitor/count/config"
    msg = {
        "name": "ADS-B Monitor vehicles count",
        "state_topic": "adsb/monitor/count",
        "unique_id": "adsb_monitor_count",
        "unit_of_measurement": "vehicles",
        "device_class": None,
        "state_class": "measurement",
        "device": {
            "identifiers": ["adsb_monitor"],
            "name": "ADS-B Receiver",
            "manufacturer": "Raspberry Pi 4B",
            "model": "FlightAware USB",
            "sw_version": "bookworm"
        },
        "origin": {
            "name": "adsbmon.py",
            "sw": f"{ADSB_MON_VERSION_MAJOR}.{ADSB_MON_VERSION_MINOR}"
        }
    }
    mqttClient.publishJson(topic, msg, retain=True)


def publishNullTracksCountDiscoveryMsg():
    topic = "homeassistant/sensor/adsb_monitor/count/config"
    mqttClient.publishJson(topic, "", retain=True)


def publishTracksCountUpdateMsg(numTracks):
    topic = "adsb/monitor/count"
    msg = numTracks
    mqttClient.publishJson(topic, msg, retain=True)


def processMsg(hexId, message, rxTime):
    if hexId in tracks:
        tracks[hexId].update(message, rxTime)
        logging.debug(f"Updated track: {hexId}")
    else:
        if not debug:
            publishTrackDiscoveryMsg(hexId)
            logging.debug(f"Published discovery message for {hexId}")
        else:
            logging.debug(f"Skipped publishing Track discovery message for {hexId}")
        newTrack = Track(message, rxTime)
        with lock:
            tracks[hexId] = newTrack
        logging.debug(f"Created and updated new track: {hexId}")
    if not debug:
        publishTrackUpdateMsg(hexId, message)
        logging.debug(f"Published update message for {hexId}")
    else:
        logging.debug(f"Skipped publishing Track update message for {hexId}")


def tracksGCLoop():
    while not stopEvent.is_set():
        now = time.time()
        logging.info(f"Garbage collect stale tracks @ {now}")
        staleTracks = [v for k, v in tracks.items() if now - v.getUpdateTime() > TRACK_STALE_TIME]
        logging.debug(f"Number of stale tracks: {len(staleTracks)}")
        for t in staleTracks:
            publishNullTrackDiscoveryMsg(t.getHexId())
            with lock:
                del tracks[t.getHexId()]
            logging.debug(f"Deleted state track: {t.getHexId}")
        stopEvent.wait(GC_RUN_INTERVAL)
    logging.debug("tracksGCLoop exited")


def printTracks():
    numTracks = len(tracks)
    logging.info(f"Number of Tracks: {numTracks}")
    if numTracks:
        print("[")
        for hexCode, track in tracks.items():
            track.print()
            if (numTracks := numTracks - 1):
                print(",")
        print("]")


#### FIXME improve the options code with
'''
args = parser.parse_args()
if args.config:
    config = configparser.ConfigParser()
    config.read(args.config)
    parser.set_defaults(**dict(config['DEFAULT']))
    args = parser.parse_args()  # Override with CLI args
'''

def getOpts():
    global debug

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-b", "--mqttHost", action="store", type=str,
        help="Path to the configuration file")
    ap.add_argument(
        "-c", "--configFilePath", action="store", type=str,
        help="Path to the configuration YAML file")
    ap.add_argument(
        "-d", "--debug", action="store_true", default=False,
        help="Suppress publishing of track messages")
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
        "-P", "--mqttPasswd", action="store", type=str,
        help="MQTT password")
    ap.add_argument(
        "-p", "--mqttPort", action="store", type=int,
        help="MQTT Broker port number")
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
        if 'configFilePath' in DEFAULTS:
            configFilePath = DEFAULTS['configFilePath']
    if configFilePath:
        if not os.path.exists(configFilePath):
            print(f"ERROR: Invalid configuration file path: {configFilePath}", file=sys.stderr)
            exit(1)
        with open(configFilePath, "r") as confFile:
            fileOpts = list(yaml.load_all(confFile, Loader=yaml.Loader))
            if len(fileOpts) >= 1:
                conf['fileOpts'] = fileOpts[0]
                if len(fileOpts) > 1:
                    print("WARNING: Multiple config docs in file. Using the first one", file=sys.stderr)

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

    debug = c['debug']

    return c


def run(options):
    global mqttClient, stopEvent

    stopEvent = threading.Event()

    ExitGracefully()

    def usr1Handler(sig, frame):
        printTracks()

    signal.signal(signal.SIGUSR1, usr1Handler)   # 'kill -USR1' to print current tracks

    if options['verbose'] > 1:
        json.dump(options, sys.stdout, indent=4, sort_keys=True)

    dumpDir = Path(options['adsbPath'])

    mqttClient = MyMqtt(MQTT_CLIENT_ID,
                        options['mqttHost'], options['mqttPort'],
                        options['mqttKeepalive'], options['mqttUsername'],
                        options['mqttPasswd'])
    if not mqttClient:
        sys.exit(1)

    publishServiceDiscoveryMsg()
    publishTracksCountDiscoveryMsg()

    if options['readHistory']:
        historyFiles = sorted(dumpDir.glob("history_*.json"),
                              key=lambda p: p.stat().st_mtime)
        for path in historyFiles:
            try:
                data = json.loads(path.read_text('utf-8'))
                ts = datetime.fromtimestamp(data['now'])
                logging.info(f"read history file {path.name}; now={ts}; {len(data['aircraft'])} msgs")
                #### TODO put data integrity checks here -- data.now, data.messages, data.aircraft[]
                for msg in data['aircraft']:
                    processMsg(msg['hex'], msg, data['now'])
            except json.JSONDecodeError:
                logging.warning(f"Invalid JSON in: {path}")
            except UnicodeDecodeError:
                logging.warning(f"Can't read: {path}")

    publishServiceStateMsg(True)
    logging.info(f"sent Service state True @ {datetime.fromtimestamp(time.time())}")

    #### TODO add check for file not changing in some amount of time and bail
    observer = PollingObserver()
    aircraftJsonPath = dumpDir / AIRCRAFT_JSON_FILE
    handler = JsonHandler(aircraftJsonPath)
    observer.schedule(handler, path=str(aircraftJsonPath), recursive=False)
    observer.start()
    logging.debug(f"Watching {str(aircraftJsonPath)}...")

    gcThread = threading.Thread(target=tracksGCLoop, daemon=True)
    gcThread.start()
    logging.debug(f"Running Garbage Collector every {GC_RUN_INTERVAL}secs")

    try:
        while observer.is_alive() and not stopEvent.is_set():
            if stopEvent.wait(1.0):  # 1s poll + check signal
                break
    finally:
        observer.stop()
        observer.join()
    logging.debug("Observer exited")

    publishTracksCountUpdateMsg(0)
    publishServiceStateMsg(False)
    logging.info("sent Service state False @ {datetime.fromtimestamp(time.time())}")
    time.sleep(0.6)  # allow mqtt message to be sent

    if opts['verbose'] > 2:
        printTracks()

    logging.debug("Shutdown complete, exiting")
    sys.exit(0)


if __name__ == "__main__":
    opts = getOpts()
    run(opts)
