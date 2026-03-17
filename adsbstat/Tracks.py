#!/usr/bin/python3
#
# Object that encapsulates active ADS-B vehicle tracks

import json
import logging
import sys
import time


class Tracks:
    def __init__(self, aircraftDB, receiverSite, staleTime):
        self.aircraftDB = aircraftDB
        self.receiverSite = receiverSite
        self.staleTime = staleTime
        self.tracks = {}

    def addMessage(self, msgTime, msg):
        hexId = msg['hex']
        if hexId not in self.tracks:
            self.tracks[hexId] = []
        self.tracks[hexId].append({'msgTime': msgTime, 'msg': msg})

    def garbageCollect(self):
        staleHexIds = []
        for hexId, messages in self.tracks.items():
            for msg in messages:
                seen = msg['msg'].get('seen')
                if not seen:
                    logging.warning("'seen' field missing from message, skipping")
                    continue
                lastSeenTime = msg['msgTime'] - seen
                now = time.time()
                if (now - lastSeenTime) > self.staleTime:
                    staleHexIds.append(hexId)
        for hexId in staleHexIds:
            self.tracks.pop(hexId, None)
            logging.debug("Delete: %s", hexId)

    def printAll(self):
        json.dump(self.tracks, sys.stdout, indent=4, sort_keys=True)



'''
            if {'lat', 'lon'} <= msg.keys():
                distance = self.rxSite.distance2dNM(msg['lat'], msg['lon'])
                logging.debug("distance: %f", distance)
                if distance <= self.rxSite.max2dDistance:
                    requiredKeys = {'alt_geom', 'category', 'gs', 'hex', 'seen_pos'}
                    missingKeys = requiredKeys  - msg.keys()
                    if missingKeys:
                        logging.error("Message is missing fields: %s", missingKeys)
                        continue

                    additionalKeys = {'baro_rate', 'emergency', 'flight', 'geom_rate', 'rssi', 'seen'}
                    hexId = msg['hex']
                    mappings = self.aircraftDB.getMappings(hexId)
                    if not mappings[0]:
                        logging.error("HexId '%s' not found in AircraftDB", hexId)
                        continue
                    record = {
                        'acType': mappings[2],
                        'acCode': mappings[3],
                        'dist2d': distance,
                        'dist3d': self.rxSite.distance3dNM(msg['lat'], msg['lon'], msg['alt_geom']),
                        'ts': data['now'],
                        'tn': mappings[1]
                    }
                    requiredFields = {k: msg.get(k) for k in requiredKeys}
                    record.update(requiredFields)
                    if ADDITIONAL_FIELDS:
                        addedFields = {k: msg.get(k) for k in additionalKeys}
                        record.update(addedFields)

                    if hexId in self.records:
                        self.records[hexId].append(record)
                    else:
                        self.records[hexId] = [record]
                    #### TMP TMP TMP
                    for h, l in self.records.items():
                        lastSeen = l[-1]['ts'] + l[-1]['seen_pos']
                        print(f"> {h}: {len(l)}, {datetime.fromtimestamp(lastSeen)}")
                    print("")

                    # GC the track records
                    for hexId, recordList in self.records.items():
                        lastSeen = l[-1]['ts'] + l[-1]['seen_pos']
                        now = time.time()
                        print(f"{l[-1]['ts']}, {l[-1]['seen_pos']}, {now}")
                        if now > lastSeen + STALE_TRACK_TIME:
                            print(f"GC: {hexId}")
                            del(self.records[hexId])
'''


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