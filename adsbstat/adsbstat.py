#!/usr/bin/env python3
#
# Script that monitors the dump1090-fa program, and gathers stats on the number
#  and type of aircraft near a given position
#
# N.B. options precedence order: cmd line -> conf file -> defaults
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

from ReceiverSite import ReceiverSite

import pdb  ## pdb.set_trace()


ADSB_STAT_VERSION_MAJOR = 0
ADSB_STAT_VERSION_MINOR = 1
ADSB_STAT_VERSION_PATCH = 0
ADSB_STAT_VERSION = f"{ADSB_STAT_VERSION_MAJOR}.{ADSB_STAT_VERSION_MINOR}.{ADSB_STAT_VERSION_PATCH}"

FILE_UNCHANGED_TIMEOUT = 90  # throw exception if aircraft file doesn't change in 90 secs

AIRCRAFT_JSON_FILE = "aircraft.json"

DEFAULTS = {
    'logFile': None,
    'logLevel': "WARNING",
    'maxDistance': 2.5,
    'name': "Home",
    'verbose': 0
}

stopEvent = None

rxSite = None


class JsonHandler(FileSystemEventHandler):
    def __init__(self, filePath):
        self.filePath = filePath
        self.lastChanged = time.time()

#    def on_any_event(self, event):
#        logging.debug("Event: %s, Path: %s, Dir: %s", event.event_type, event.src_path, event.is_directory)

    def on_created(self, event):
        self.lastChanged = time.time()
        if event.src_path.endswith(AIRCRAFT_JSON_FILE) and event.is_directory is False:
            self.readJson()

    def readJson(self):
        try:
            text = self.filePath.read_text(encoding='utf-8')
            data = json.loads(text)
            ts = datetime.fromtimestamp(data['now'])
            logging.debug("aircraft file updated @ %s; data['now']=%s; # msgs: %d",
                          datetime.fromtimestamp(time.time()), ts, len(data['aircraft']))
            #### TODO put data integrity checks here -- data.now, data.messages, data.aircraft[]
            for msg in data['aircraft']:
                print(f">>>> {rxSite.distance2dNM(msg['lat'], msg['lon'])}")
                if rxSite.distance2dNM(msg['lat'], msg['lon']) <= rxSite.max2dDistance:
                    processMsg(msg['hex'], msg, data['now'])
        except Exception as e:
            logging.error("Failed to read %s: %s", self.filePath, e)


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
                logging.info("unknown signal: %s", sig)


def processMsg(hexId, message, rxTime):
    print(hexId)  #### FIXME


def getOpts():
    global debug

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-c", "--configFilePath", action="store", type=str,
        help="Path to the configuration YAML file")
    ap.add_argument(
        "-L", "--logLevel", action="store", type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level")
    ap.add_argument(
        "-l", "--logFile", action="store", type=str,
        help="Path to the logfile (create it if it doesn't exist)")
    ap.add_argument(
        "-m", "--maxDistance", action="store", type=float,
        help="Max distance from receiver in NM")
    ap.add_argument(
        "-n", "--name", action="store", type=str,
        help="Name of the receiver site")
    ap.add_argument(
        "-p", "--position", metavar=("lat", "lon", "alt"), type=float, nargs=3,
        help="Position: <lat> <lon> <alt>")
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

    if 'adsbPath' not in c:
        logging.error("Must specify the path to where dump1090-fa stores its files")
        sys.exit(1)
    return c


def run(options):
    global stopEvent, rxSite

    stopEvent = threading.Event()

    ExitGracefully()

    if options['verbose'] > 1:
        json.dump(options, sys.stdout, indent=4, sort_keys=True)

    rxSite = ReceiverSite(options['name'], options['maxDistance'],
                          options['position'][0], options['position'][1],
                          options['position'][2])
    if options['verbose'] > 1:
        rxSite.print()

    dumpDir = Path(options['adsbPath'])

    #### TODO add check for file not changing in some amount of time and bail
    observer = PollingObserver()
    aircraftJsonPath = dumpDir / AIRCRAFT_JSON_FILE
    handler = JsonHandler(aircraftJsonPath)
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

    logging.debug("Shutdown complete, exiting")
    sys.exit(0)


if __name__ == "__main__":
    opts = getOpts()
    run(opts)
