#!/usr/bin/env python3
#
# Script that monitors the dump1090-fa program, maintains tracks of currently
#  visible crafts, and emits MQTT messages that contain track updates.
#
# N.B. options precedence order: cmd line -> conf file -> defaults


#### TODO make a library function that acts as a framework for options


import argparse
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import requests
import signal
import sys
import time
import yaml

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from Track import Track

import pdb  ## pdb.set_trace()


ADSB_MON_VERSION_MAJOR = 0
ADSB_MON_VERSION_MINOR = 1
ADSB_MON_VERSION_PATCH = 0
ADSB_MON_VERSION = f"{ADSB_MON_VERSION_MAJOR}.{ADSB_MON_VERSION_MINOR}.{ADSB_MON_VERSION_PATCH}"

AIRCRAFT_JSON_FILE = "aircraft.json"

DEFAULTS = {
    'logFile': None,
    'logLevel': "WARNING",
    'readHistory': False,
    'verbose': 0
}

running = True
tracks = {}


class JsonHandler(FileSystemEventHandler):
    def __init__(self, filepath):
        self.filepath = Path(filepath)

    def on_created(self, event):
        print("On created")
        if event.src_path.endswith('aircraft.json'):
            self.read_aircraft_json()

    def on_modified(self, event):
        print("On modified")
        if event.src_path == str(self.filepath):
            self.read_json()

    def read_json(self):
        try:
            data = json.loads(self.filepath.read_text('utf-8'))
            ts = datetime.fromtimestamp(data['now'])
            logging.info(f"aircraft.json updated @ {datetime.fromtimestamp(time.time())}; now={ts}; {len(data['aircraft'])} msgs")
            #### TODO put data integrity checks here -- data.now, data.messages, data.aircraft[]
            for msg in data['aircraft']:
                processMsg(msg, data['now'])
        except Exception as e:
            logging.error(f"Failed to read {self.filepath}: {e}")
        printTracks()  #### TMP TMP TMP

def processMsg(message, rxTime):
    if message['hex'] in tracks:
        tracks[message['hex']].update(message, rxTime)
    else:
        tracks[message['hex']] = Track(message, rxTime)

def printTracks():
    logging.info(f"Number of Tracks: {len(tracks)}")
    for hexCode, track in tracks.items():
        logging.info(f"Track: {hexCode}")
        track.print()

def stop():
    global running
    running = False

def getOpts():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-c", "--configFilePath", action="store", type=str,
        help="Path to the configuration file")
    ap.add_argument(
        "-L", "--logLevel", action="store", type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level")
    ap.add_argument(
        "-l", "--logFile", action="store", type=str,
       help="Path to the logfile (create it if it doesn't exist)")
    ap.add_argument(
        "-r", "--readHistory", action="store_true", default=False,
        help="Read history files on startup")
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
            print(f"ERROR: Invalid configuration file path: {configFilePath}")
            exit(1)
        with open(configFilePath, "r") as confFile:
            fileOpts = list(yaml.load_all(confFile, Loader=yaml.Loader))
            if len(fileOpts) >= 1:
                conf['fileOpts'] = fileOpts[0]
                if len(fileOpts) > 1:
                    print(f"WARNING: Multiple config docs in file. Using the first one")

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
    if options['verbose'] > 1:
        json.dump(options, sys.stdout, indent=4, sort_keys=True)

    dumpDir = Path(options['adsbPath'])

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
                    processMsg(msg, data['now'])
            except json.JSONDecodeError:
                logging.warning(f"Invalid JSON in: {path}")
            except UnicodeDecodeError:
                logging.warning(f"Can't read: {path}")

    printTracks()  #### TMP TMP TMP

    observer = Observer()
    aircraftJsonPath = dumpDir / AIRCRAFT_JSON_FILE
    handler = JsonHandler(str(aircraftJsonPath))
    observer.schedule(handler, path=str(aircraftJsonPath), recursive=False)
    observer.start()
    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    opts = getOpts()
    run(opts)

    '''
    def signalHandler(sig, frame):
        '' Catch SIGHUP to force a restart and SIGINT to stop.""
        ''
        if sig == signal.SIGHUP:
            logging.info("SIGHUP")
            stop()
        elif sig == signal.SIGINT:
            logging.info("SIGINT")
            stop()
#            exit(1)
    '''
