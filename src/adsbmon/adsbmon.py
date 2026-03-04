#!/usr/bin/python3
#
# Script that monitors the dump1090-fa program, maintains tracks of currently
#  visible crafts, and emits MQTT messages that contain track updates.
#
# N.B. options precedence order: cmd line -> conf file -> defaults


#### TODO make a library function that acts as a framework for options


import argparse
import json
import logging
import os
from pathlib import Path
import requests
import sys
import time
import yaml

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


ADSB_MON_VERSION_MAJOR = 0
ADSB_MON_VERSION_MINOR = 1
ADSB_MON_VERSION_PATCH = 0
ADSB_MON_VERSION = f"{ADSB_MON_VERSION_MAJOR}.{ADSB_MON_VERSION_MINOR}.{ADSB_MON_VERSION_PATCH}"

DEFAULTS = {
    'configFilePath': "./config.yaml",
    'logFile': None,
    'logLevel': "INFO",  #"DEBUG"  #"WARNING",
    'readHistory': False,
    'verbose': 0
}


class JsonHandler(FileSystemEventHandler):
    def __init__(self, filepath):
        self.filepath = Path(filepath)

    def on_modified(self, event):
        if event.src_path == str(self.filepath):
            self.read_json()

    def read_json(self):
        try:
            data = json.loads(self.filepath.read_text('utf-8'))
            print("File updated:", data)  # or process data
        except Exception as e:
            print(f"Error reading {self.filepath}: {e}")


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
    conf = {'version': ADSB_MON_VERSION, 'cliOpts': cliOpts, 'fileOpts': {},
            'config': {}, 'defaults': DEFAULTS}
    if conf['cliOpts']['configFilePath']:
        configFilePath = cliOpts['configFilePath']
    else:
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
            logging.info(f"Processing history file: {path.name}")
            try:
                data = json.loads(path.read_text('utf-8'))
                #### TODO process message data
            except json.JSONDecodeError:
                logging.warning(f"Invalid JSON in: {path}")
            except UnicodeDecodeError:
                logging.warning(f"Can't read: {path}")

    

    #### TODO in a loop, watch for changes in aircraft.json file
    #### TODO update tracks/vehicles
    #### TODO emit tracks
    #### TODO GC tracks/vehicles

if __name__ == "__main__":
    opts = getOpts()
    run(opts)
