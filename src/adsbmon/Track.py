#!/usr/bin/python3
#
# Object that encapsulates a vehicle track

import json
import logging
import sys
import time


class Track:
    def __init__(self, message, rxTime):
        self.track = {}
        self.update(message, rxTime)

    def update(self, message, rxTime):
        self.track['updateTime'] = time.time()
        if 'seen_pos' in message.keys():
            self.track['seenPosTime'] = rxTime - message['seen_pos']
        if 'seen' in message.keys():
            self.track['seenTime'] = rxTime - message['seen']
        self.track.update(message)

    def print(self):
        json.dump(self.track, sys.stdout, indent=4, sort_keys=True)