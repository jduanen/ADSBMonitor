#!/usr/bin/python3
#
# Class that defines the callback for changes to the ADS-B JSON file generated
#  by readsb (i.e., aircraft.json)

from datetime import datetime
import json
import logging
from pathlib import Path
import time

from watchdog.events import FileSystemEventHandler


class JsonFileHandler(FileSystemEventHandler):
    def __init__(self, filePath, newMessagesHandler):
        self.filePath = filePath
        self.newMessages = newMessagesHandler
        self.lastChanged = time.time()

    '''
    def on_any_event(self, event):
        logging.debug("Event: %s, Path: %s, Dir: %s", event.event_type, event.src_path, event.is_directory)
    '''

    def on_created(self, event):
        if Path(event.src_path).resolve() != self.filePath.resolve():
            return  # ignore changes to history_*.json and other files in the same directory
        self.lastChanged = time.time()
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
            return
        ts = datetime.fromtimestamp(data['now'])
        logging.debug("aircraft file updated @ %s; data['now']=%s; # msgs: %d",
                      datetime.fromtimestamp(time.time()), ts, len(data['aircraft']))
        missingKeys = {'now', 'messages', 'aircraft'} - data.keys()
        if missingKeys:
            logging.error("Ill-formed file, missing keys: %s", missingKeys)
            return
        self.newMessages(data)

