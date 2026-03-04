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
import sys
import yaml


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

def getOpts():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-a", "--adsbPath", action="store", type=str,
       help="Path to where the dump1090-fa program stores its data")
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
        logging.error("Must specify the path to the aircraft.json file")
        sys.exit(1)
    return c

def run(options):
    json.dump(options, sys.stdout, indent=4, sort_keys=True)

if __name__ == "__main__":
    opts = getOpts()
    run(opts)
