#!/usr/bin/python3
#
# Object that encapsulates active ADS-B vehicle tracks
#
# tracks
#   - <hexId>
#     - inRange: <bool>
#     - msgTime: <time>
#     - msg: <adsbMsg>
#       * hex: <hexId>
#       ...
#   - <hexId>
#     - inRange: <bool>
#     - msgTime: <time>
#     - msg: <adsbMsg>
#       * hex: <hexId>
#       ...
#   ...

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

    def _garbageCollect(self):
        staleHexIds = []
        with self._lock:
            for hexId, message in list(self.tracks.items()):
                seen = message['msg'].get('seen', None)
                if not seen:
                    continue
                lastSeenTime = message['msgTime'] - seen
                if (time.time() - lastSeenTime) > self.staleTime:
                    staleHexIds.append(hexId)
                    del self.tracks[hexId]
        for hexId in staleHexIds:
            self.staleTrackHandler(hexId)
            logging.info("Delete: %s", hexId)
        self._startTimer()

    def updateTrack(self, inRange, msgTime, msg):
        hexId = msg['hex']
        with self._lock:
            if hexId not in self.tracks:
                self.tracks[hexId] = {'inRange': inRange, 'msgTime': msgTime, 'msg': msg}
            else:
                self.tracks[hexId]['inRange'] = inRange
                self.tracks[hexId]['msgTime'] = msgTime
                self.tracks[hexId]['msg'] |= msg

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

    def trackExists(self, hexId):
        return hexId in self.tracks

    def isInRange(self, hexId):
        with self._lock:
            track = self.tracks.get(hexId)
            return track['inRange'] if track else None

    def inRangeTrackIds(self):
        with self._lock:
            inRange = [hexId for hexId, track in self.tracks.items() if track['inRange']]
        return inRange

    def removeTrack(self, hexId):
        with self._lock:
            self.tracks.pop(hexId, None)
        self.staleTrackHandler(hexId)
        logging.info("remove: %s", hexId)

    def removeAllTracks(self):
        with self._lock:
            hexIds = list(self.tracks.keys())
            self.tracks.clear()
        for hexId in hexIds:
            self.staleTrackHandler(hexId)
            logging.info("Remove: %s", hexId)

    def printAll(self):
        json.dump(self.tracks, sys.stdout, indent=4, sort_keys=True)
