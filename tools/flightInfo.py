#!/usr/bin/python3

# Script to get flight info from adsbdb.com
#
# Usage: flightInfo.py [-v] [-p] [-L <logLevel>] [-l <logFile>] <subcommand> [-f <field>{ <field>}* ] <craftId>"
#   Modes/Fields:
#     aircraft:
#       type: <type>
#       typeCode: <typeIcaoCode>
#       mfgr: <manufacturer>
#       modeS: <modeSId>
#       registration: <tailNumber>
#       countryName: <countryName>
#       countryCode: <countryIsoCode>
#     airline:
#       name: <airlineName>
#       code: <airlineCode>  ## ICAO or IATA????
#       countryName: <countryName>
#       countryCode: <countryIsoCode>
#       callsign: <callsign>
#     callsign:
#       route: <originName> (<orginCode>) -> <destName> (<destCode>)
#       airlineName: <airlineName>
#       airlineCode: <airlineCode>
#       airlineCountry: <airlineCountryName>
#       originName: <originName>
#       originCode: <originCode>
#       destName: <destName>
#       destCode: <destCode>
#     nnumber: <hexCode>
#     hexCode: <nNumber>
#
# N.B. the adsbdb.com site is only about 50% accurate on route information
#### FIXME switch over to Flight24 or another paid site for more accurate info

#### TODO hexCodeToTailNumber.sh
#### TODO tailNumberToHexCode.sh
#### TODO add config file option and set up overrides/precedent logic
#### FIXME do this with aircraft and callsign API call
####  https://api.adsbdb.com/v0/aircraft/{ MODE_S || REGISTRATION }?callsign={ CALLSIGN_ICAO || CALLSIGN_ICAO }
#### FIXME make it work with MODE_S, REG, and CALLSIGN as inputs -- change subcommands to do this instead
#### TODO combine into one big one for this and eliminate aircraft and airline as they are contained in the larger response
#### TODO find a way of using the suffix codes -- tool to look for suffixes and report numbers ending in alpha character
# Suffix:
#  F: Freighter or Cargo
#  H: Ad-hoc, charter, or hotel leg
#  K: Ferry, Repositioning, or Test flight
#  L: Return Leg
#  M: Military Charter, Special Ops variant, or Additional flight
#  P: Positioning or empty leg
#  R: Revised or Unscheduled variant
#  T: Training or Circuits
#  W: Revised or Unscheduled variant

import argparse
import json
import logging
import requests
import sys


DEFAULTS = {
    'logLevel': "INFO",  #"DEBUG"  #"WARNING",
}


printHelp = None
verbose = False

def getOps():
    global printHelp, verbose
    parser = argparse.ArgumentParser()
    printHelp = parser.print_help

    # common args
    parser.add_argument(
        "-L", "--logLevel", action="store", type=str,
        default=DEFAULTS['logLevel'],
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level")
    parser.add_argument(
        "-l", "--logFile", action="store", type=str,
        help="Path to location of logfile (create it if it doesn't exist)")
    parser.add_argument(
        "-p", "--pprint", action="store_true", default=False,
        help="Pretty-print the JSON output")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="Enable printing of debug info")

    subparsers = parser.add_subparsers(dest='subcommand', help="Sub-command")

    # aircraft
    aircraftParser = subparsers.add_parser('aircraft', help="Aircraft Information")
    aircraftParser.add_argument(
        "-f", "--fields", nargs='+', default="route",
        choices=["typeName", "typeCode", "manufacturer", "hexCode", "registration"],
        help="List of (one or more) field(s) to be returned")

    # airline
    airlineParser = subparsers.add_parser('airline', help="Airline Information")
    airlineParser.add_argument(
        "-f", "--fields", nargs='+', default="route",
        choices=["name", "code", "countryName", "countryCode"],
        help="List of (one or more) field(s) to be returned")

    # callsign
    callsignParser = subparsers.add_parser('callsign', help="Callsign Information")
    callsignParser.add_argument(
        "-f", "--fields", nargs='+', default="route",
        choices=["route", "airlineName", "airlineCode", "airlineCountry", "originName", "originCode", "destName", "destCode"],
        help="List of (one or more) field(s) to be returned")

    # nnumber
    nNumberParser = subparsers.add_parser('nnumber', help="N-Number to Hex Code Conversion")

    # hexcode
    hexCodeParser = subparsers.add_parser('hexcode', help="Hex Code to N-Number Conversion")

    parser.add_argument('callsign', help="Callsign of vehicle of interest")
    opts = parser.parse_args()

    if opts.logFile:
        logging.basicConfig(filename=opts.logFile,
                            format='%(asctime)s %(levelname)-8s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            level=opts.logLevel)
    else:
        logging.basicConfig(level=opts.logLevel,
                            format='%(asctime)s %(levelname)-8s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

    #### TODO test for valid inputs
    ####  * check if hexcode is valid hex chars and at most six of them
    ####  * check if callsign is no more than eight legal chars

#    if opts.subcommand in ("nnumber", "hexcode") and hasattr(opts, "fields"):
#        logging.warning(f"sub-command {opts.subcommand} does not take fields, ignoring")

    verbose = opts.verbose
    if verbose:
        print(f"    Sub-command: {opts.subcommand}")
        if opts.pprint:
            print("    Pretty-print output")
        if opts.logLevel:
            print(f"    Log Level:   {opts.logLevel}")
        if opts.logFile:
            print(f"    Log File:    {opts.logFile}")
        print(f"    Callsign:    {opts.callsign}")
        print(f"    Fields:      {getattr(opts, 'fields', 'n/a')}")

    return opts

def adsbdbGet(path, verbose=False):
    try:
        response = requests.get(path, timeout=10)
        response.raise_for_status()  # raises HTTPError for 4xx/5xx
        data = response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed: {e}")
        return None
    except ValueError as e:  # JSON decode error
        logging.error(f"Invalid JSON: {e}")
        return None
    if isinstance(data['response'], str):
        logging.error(f"{data['response']}")
        return None
    if verbose > 1:
        json.dump(data, sys.stdout, indent=4, sort_keys=True)
    return data

def callsignGet(callsign):
    data = adsbdbGet(f"https://api.adsbdb.com/v0/callsign/{callsign}")
    if not data:
        sys.exit(1)
    return data

def run(options):
    match options.subcommand:
        case "aircraft":
#            "typeName", "typeCode", "manufacturer", "hexCode", "registration"
            pass
        case "airline":
#            "code", "countryName", "countryCode"
            pass
        case "callsign":
            data = callsignGet(options.callsign)
            flightroute = data['response']['flightroute']
            ret = {}
            if "route" in options.fields:
                origin = flightroute['origin']
                destination = flightroute['destination']
                ret['route'] = f"{origin['name']} ({origin['iata_code']}) -> {destination['name']} ({destination['iata_code']})"
            if "airlineName" in options.fields:
                airline = flightroute['airline']
                ret['airlineName'] = airline['name']
            if "airlineCode" in options.fields:
                airline = flightroute['airline']
                ret['airlineCode'] = airline['icao']
            if "airlineCountry" in options.fields:
                airline = flightroute['airline']
                ret['airlineCountry'] = airline['country']
            if "originName" in options.fields:
                origin = flightroute['origin']
                ret['originName'] = origin['name']
            if "originCode" in options.fields:
                origin = flightroute['origin']
                ret['originCode'] = origin['iata_code']
            if "destName" in options.fields:
                dest = flightroute['destination']
                ret['destName'] = dest['name']
            if "destCode" in options.fields:
                dest = flightroute['destination']
                ret['destCode'] = dest['iata_code']
        case _:
            printHelp()
            sys.exit(1)

    if options.pprint:
        json.dump(ret, sys.stdout, indent=4, sort_keys=True)
    else:
        json.dump(ret, sys.stdout)
    print("")

if __name__ == '__main__':
    opts = getOps()
    run(opts)
