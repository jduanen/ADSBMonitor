#!/usr/bin/python3
#
# Object that encapsulates active ADS-B vehicle tracks
#
# tracks
#   - <hexId>
#     - msgTime: <time>
#     - msg: <adsbMsg>
#   - <hexId>
#     - msgTime: <time>
#     - msg: <adsbMsg>
#   ...

import copy
import json
import logging
import sys
import threading
import time


#### TODO tune this value appropriately
GC_INTERVAL = 10  # run the garbage collector every 10 secs


class Tracks:
    def __init__(self, aircraftDB, receiverSite, staleTime, staleTrackHandler):
        ''' ?
        '''
        self.aircraftDB = aircraftDB
        self.receiverSite = receiverSite
        self.staleTime = staleTime
        self.staleTrackHandler = staleTrackHandler

        self.tracks = {}
        self._lock = threading.Lock()
        self._timer = None
        self._startTimer()

    def __del__(self):
        self._stopTimer()

    def _startTimer(self):
        self._timer = threading.Timer(GC_INTERVAL, self._garbageCollect)
        self._timer.start()

    def _restartTimer(self):
        self._stopTimer()
        self._startTimer()

    def _stopTimer(self):
        if self._timer:
            self._timer.cancel()

    def _removeTracks(self, hexIds):
        for hexId in hexIds:
            self.staleTrackHandler(hexId)
            with self._lock:
                self.tracks.pop(hexId, None)
            logging.info("Delete: %s", hexId)

    def _garbageCollect(self):
        staleHexIds = []
        with self._lock:
            for hexId, messages in self.tracks.items():
                mostRecentMsg = messages[-1]
                seen = mostRecentMsg['msg'].get('seen')
                if not seen:
                    continue
                lastSeenTime = mostRecentMsg['msgTime'] - seen
                now = time.time()
                if (now - lastSeenTime) > self.staleTime:
                    staleHexIds.append(hexId)
        self._removeTracks(staleHexIds)
        self._startTimer()

    def updateTrack(self, msgTime, msg):
        hexId = msg['hex']
        with self._lock:
            if hexId not in self.tracks:
                self.tracks[hexId] = {}
            self.tracks[hexId] |= {'msgTime': msgTime, 'msg': msg}

    def lastMessageTime(self, hexId):
        with self._lock:
            if hexId not in self.tracks:
                return None
            return self.tracks[hexId]['msgTime']

    def startGarbageCollect(self):
        self._restartTimer()

    def stopGarbageCollect(self):
        self._stopTimer()

    def numberOfTracks(self):
        return len(self.tracks)

    def removeAllTracks(self):
        while self.tracks:
            with self._lock:
                allHexIds = list(self.tracks.keys())
                self._removeTracks(allHexIds)

    def printAll(self):
        json.dump(self.tracks, sys.stdout, indent=4, sort_keys=True)
