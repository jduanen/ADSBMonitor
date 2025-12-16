#!/usr/bin/python3
#
# Script to watch the aircraft track output file from dump1090 and publish the
#  aircraft tracks as MQTT messages
#

import json
import time
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

RASPI_IP = "192.168.1.50"
JSON_URL = f"http://{RASPI_IP}/tar1090/data/aircraft.json"
TEMP_FILE = "/tmp/aircraft.json"  # Local temp file

class AircraftHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('aircraft.json'):
            print(f"\n[{time.strftime('%H:%M:%S')}] File changed! Processing...")
            self.process_aircraft_json()
    
    def process_aircraft_json(self):
        try:
            # Fetch fresh data
            resp = requests.get(JSON_URL, timeout=5)
            data = resp.json()
            
            # Pretty print
            print(json.dumps(data, indent=2))
            
            # Your custom processing here
            aircraft = [p for p in data['aircraft'] if p.get('lat')]
            print(f"Plottable aircraft: {len(aircraft)}")
            
            for plane in aircraft[:3]:
                print(f"  {plane.get('icao')} {plane.get('flight')} @ {plane.get('alt_baro')}ft")
                
        except Exception as e:
            print(f"Processing error: {e}")

def download_aircraft_json():
    """Initial download to start monitoring"""
    resp = requests.get(JSON_URL)
    with open(TEMP_FILE, 'w') as f:
        f.write(resp.text)
    return True

if __name__ == "__main__":
    # Initial download
    print("Downloading initial aircraft.json...")
    download_aircraft_json()
    
    # Start monitoring
    event_handler = AircraftHandler()
    observer = Observer()
    observer.schedule(event_handler, path='/tmp', recursive=False)
    observer.start()
    
    try:
        print(f"Monitoring {TEMP_FILE} for changes... (Ctrl+C to stop)")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
