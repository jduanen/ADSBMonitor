#!/usr/bin/python3
#
# Class that defines the callback for changes to the ADS-B JSON file generated
#  by readsb (i.e., aircraft.json)

from datetime import datetime
import json
import logging
import time

from watchdog.events import FileSystemEventHandler


class JsonFileHandler(FileSystemEventHandler):
    def __init__(self, filePath, tracks, addedMessageHandler):
        self.filePath = filePath
        self.tracks = tracks
        self.addedMessage = addedMessageHandler
        self.lastChanged = time.time()

    '''
    def on_any_event(self, event):
        logging.debug("Event: %s, Path: %s, Dir: %s", event.event_type, event.src_path, event.is_directory)
    '''

    def on_created(self, event):
        self.lastChanged = time.time()
        #### TODO can I remove this test?
        if event.is_directory is False:
            self.readJson()

    def readJson(self):
        try:
            text = self.filePath.read_text(encoding='utf-8')
            data = json.loads(text)
            if not data:
                logging.error("No data read")
                return
        except Exception as e:
            logging.error("Failed to read '%s': %s", self.filePath, e)
        ts = datetime.fromtimestamp(data['now'])
        logging.debug("aircraft file updated @ %s; data['now']=%s; # msgs: %d",
                      datetime.fromtimestamp(time.time()), ts, len(data['aircraft']))
        missingKeys = {'now', 'messages', 'aircraft'} - data.keys()
        if missingKeys:
            logging.error("Data is missing keys: %s", missingKeys)
        else:
            for msg in data['aircraft']:
                self.tracks.addMessage(data['now'], msg)
                self.addedMessage(msg['hex'], self.tracks)
