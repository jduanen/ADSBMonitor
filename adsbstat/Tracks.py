#!/usr/bin/python3
#
# Object that encapsulates active ADS-B vehicle tracks

import json
import sys
import time


class Tracks:
    def __init__(self, aircraftDB, receiverSite, staleTime):
        self.aircraftDB = aircraftDB
        self.receiverSite = receiverSite
        self.stateTime = staleTime
        self.tracks = {}

    def addMessage(self, msgTime, msg):
        print("addMessage")  #### TBD

    def garbageCollect(self):
        print("GC")  #### TBD

    def print(self):
        json.dump(self.tracks, sys.stdout, indent=4, sort_keys=True)
'''
    def update(self, message, rxTime):
        self.track['updateTime'] = time.time()
        if 'seen_pos' in message.keys():
            self.track['seenPosTime'] = rxTime - message['seen_pos']
        if 'seen' in message.keys():
            self.track['seenTime'] = rxTime - message['seen']
        self.track.update(message)

    def getHexId(self):
        return self.track['hex']

    def getUpdateTime(self):
        return self.track.get('updateTime', 0.0)
'''