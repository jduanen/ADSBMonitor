# ADSBMonitor
Tool for logging and analyzing ADS-B data

**WIP**

## Hardware
* Raspberry Pi 4B (1GB DRAM, Trixie)
* Flight Aware SDR USB dongle (RTL2832U, R820T)
* Nano Three (n3) SDR USB dongle (RTL2838, R820T)
* ???? splitter
* ???? dual band (1090MHz and 978MHz) ?db antenna

## Software
* readsb: decodes 1090MHz ADS-B, provides API
  - interfaces directly to the Flight Aware dongle (s/n: 00001090)
  - http://adsbmon.lan:8504: real-time map
  - http://adsbmon.lan/tar1090: real-time map
  - http://adsbmon.lan:8042/?<arg>: API
* dump978-fa: decodes 978MHz UAT
  - interfaces directly to the Nano Three dongle (s/n: 00000978)
  - produces ????
* adsbmon.py: ?

## TODO
  * put setup information for ADS-B server in here
  * publish raw data and nearest data on separate topics
    - raw topic
      * emit MQTT message with all tracks (as attributes?) on each file change
    - nearest topic
      * sort by nearest N and filter by max distance D
      * emit message with nearest up to N, at most distance D from home
      * include interesting info for top one and basic info for the rest in the list
  * on HA server: create (virtual?) MQTT device that has variable number of entities (planes)
  * model and print case for RasPi and RTL_SDR dongle
  * design and build small dedicated ambient display unit for the Top N (=1?)

## Installation

### HW Setup
* need separate SDR dongles for ES1090 and UAT978
  - 1090 Mhz dongle: use 8-digit serial # 00001090
  -  978 Mhz dongle: use 8-digit serial # 00000978
* unplug all dongles
* Blacklist DVB-T drivers (Trixie-specific)
  - for RTL.SDR dongles
'''
echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/blacklist-rtl.conf
echo 'blacklist rtl2832' | sudo tee -a /etc/modprobe.d/blacklist-rtl.conf
echo 'blacklist rtl2830' | sudo tee -a /etc/modprobe.d/blacklist-rtl.conf
sudo update-initramfs -u
'''
  - for RTL28xx dongles
'''
cat > /etc/modprobe.d/no-dvb.conf << EOF
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
blacklist dvb_usb_rtl2832u
EOF

sudo update-initramfs -u
sudo reboot
'''
* install udev rules
  - for RTL.SDR dongles
'''
sudo apt install rtl-sdr
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", GROUP="plugdev", MODE="0666"' | sudo tee /etc/udev/rules.d/90-rtl.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

'''
  - for RTL28xx dongles
'''
sudo tee /etc/udev/rules.d/99-rtl-sdr.rules << EOF
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", \
  GROUP="plugdev", MODE="0666", \
  RUN+="/bin/sh -c 'echo 0 > /sys/%c/device/authorized; echo 1 > /sys/%c/device/authorized'"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
'''
* install dongle serialization SW
  - 'sudo apt install rtl-sdr'
* reboot and test
'''
sudo reboot
rtl_test -t
'''
* plug in 1090 dongle and type:
  - 'rtl_eeprom -s 00001090'
* unplug 1090 dongle
* plug in 978 dongle and type:
  - 'rtl_eeprom -s 00000978'
* unplug both dongles and replug them both in
* configure dump1090-fa and dump978-fa for their proper dongle
'''
sudo sed -i 's/^RECEIVER_SERIAL=.*/RECEIVER_SERIAL=00001090/' /etc/default/dump1090-fa 
sudo sed -i 's/driver=rtlsdr[^ ]* /driver=rtlsdr,serial=00000978 /' /etc/default/dump978-fa 
sudo reboot 
'''

### SW Install

#### Trixie
* set up python3 and the venv for adsbmon.py
  - 'sudo apt update && sudo apt install python3-full python3-pip python3-venv'
  - 'python3 -m venv myenv'
  - 'source ./myenv/bin/activate'
  - pip install -r requirements.txt
* install readsb (better than dump1090-fa for my purposes)
'''
sudo bash -c "$(wget -nv -O - https://github.com/wiedehopf/adsb-scripts/raw/master/readsb-install.sh)"
sudo reboot
'''
* install dump978-fa
  - 'sudo apt update && sudo apt install dump978-fa'
* build and install uat2esnt
  - 'git clone https://github.com/mutability/dump978'
  - 'cd dump978'
  - 'make'  # builds uat2esnt
  - 'sudo cp uat2esnt /usr/local/bin'
* get and install aircraftdb
  - 'sudo wget -O /usr/local/share/tar1090/aircraft.csv.gz https://github.com/wiedehopf/tar1090-db/raw/csv/aircraft.csv.gz'
  - add to '/etc/default/readsb': "--db-file /usr/local/share/tar1090/aircraft.csv.gz"

### Configure Applications

Edit config files, restart all the services, and check if they're running correctly.

Check status of all services:
'sudo systemctl status readsb tar1090 dump978-fa skyaware978'

#### readsb: 1090 decoder and map and API server
* configure by editing '/etc/default/readsb'
  - add cli options
    * RECEIVER_OPTIONS: --lat=<lat> --lon=<lon>
    * NET_OPTION: --net-api-port 8042 --net-ro-size 500 --net-ro-interval 0.2 --net-connector localhost,30978,uat_in
  - modify options
    * RECEIVER_OPTIONS: --device 00001090
    * DECODER_OPTIONS: --max-range=64

#### dump978-fa: 978 decoder, feeds readsb
* edit '/etc/default/dump978-fa'
  - ENABLED=yes
  - RECEIVER_OPTIONS="--sdr driver=rtlsdr,serial=00000978 --format CS8"
  - NET_OPTIONS="--raw-port 30978 --json-port 30979"  # Raw UAT out on 30978

#### tar1090: enhanced map, reads merged 1090 and 978 data from readsb
* install
  - 'sudo bash -c "$(wget -nv -O - https://github.com/wiedehopf/tar1090/raw/master/install.sh)"'
* configure (to enable UAT978)
  - 'sudo ex /etc/default/tar1090'
    * ENABLE_978=yes
  - 'sudo systemctl restart tar1090'
  - 'sudo ex /usr/local/share/tar1090/html/config.js'  ## save copy of original first
    * autoselectCoords = [37.46, -122.17];
    * MapDim = false;
    * SiteCircles = true; // true to show circles (only shown if the center marker is shown)
    * SiteCirclesDistances = new Array(2,4,8,16,32,64);
    * <consider changing columns shown in table at startup>
    * <route info>
      - "https://adsb.im/api/0/routeset" -- "Not Allowed"
      - "https://api.adsb.lol/api/0/routeset" -- "Not Allowed"
        * "https://api.adsb.lol/docs" -- API docs
* update
  - sudo bash -c "$(wget -nv -O - https://github.com/wiedehopf/tar1090/raw/master/install.sh)"
  - configuration should be preserved

#### adsbmon.py: MQTT interface to Home Assistant
* create config yaml file and give it in the startup cli
  --> will make a service of it when it's working
* ????

## Operation
* skyaware978 map
  - http://adsbrx.lan:8504
  - data from readsb
* tar1090 map
  - enhanced real-time map: 'http://adsbrx.lan/tar1090'
  - ????: 'http://adsbrx.lan/tar1090?pTracks'
  - data from readsb
  - renders much faster, dark mode, multi-select, adjustable history
  - combines readsb and dump978-fa
* readsb API: lots of useful features
  - <synopsis and pointer to docs>
* adsbmon.py: my tool for interfacing to Home Assistant (and others) via MQTT messages
  - ????: ./adsbmon.py -v -L INFO -c ./config.yaml /run/readsb/
  - ????
* ADS-B Exchange free map: https://globe.adsbexchange.com/
  - fed by large number of receivers
  - less censoring (for now)
* <?tools?>

## adsbmon.py Application

ADSBMonitor watches ADS-B data from `readsb` (or `dump1090-fa`) running on a Raspberry Pi and publishes aircraft tracks to Home Assistant via MQTT.

### Setup

```bash
python3 -m venv adsbVenv
source adsbVenv/bin/activate
pip install -r requirements.txt
```

### Running

```bash
# adsbmon: MQTT publisher
python adsbmon/adsbmon.py -c adsbmon/config.yaml /run/readsb/
```

Options precedence: **CLI args → config file → defaults**. The `position` arg (`-p lat lon alt`) is required for `adsbmon`; it can be set in the config YAML instead.

Send `SIGUSR1` to a running process (`kill -USR1 <pid>`) to dump all current tracks to stdout.

### Architecture

The data flow:
1. `readsb` writes `aircraft.json` to `/run/readsb/` at ~1Hz
2. `JsonFileHandler` (watchdog `PollingObserver`) detects file changes and parses the JSON
3. Each aircraft message is enriched (distances computed, DB lookup) and filtered against `ReceiverSite` spatial volume constraints
4. `Tracks` manages active tracks in memory with thread-safe access and a 10-second GC timer
5. `AdsbMqtt` publishes Home Assistant MQTT discovery messages and per-track state updates

#### Shared modules (`common/`)

- **`ReceiverSite`** — encapsulates the receiver's GPS position and spatial volume filter constraints (`FilterConstraints` namedtuple with `min`/`max`). Uses `geographiclib` for geodesic distance; also computes slant distance (Pythagorean from ground distance + altitude). `withinTrackingVolume()` checks all three constraint types (ground NM, slant NM, altitude ft).
- **`Tracks`** — thread-safe dict of active tracks keyed by ICAO hex ID. Tracks with `tracking=True` are inside the filter volume. GC runs every 10 seconds; calls `staleTrackHandler(hexId)` before deleting a track. `removeTrack()` and `removeAllTracks()` also invoke the stale handler (used for cleanup on shutdown).
- **`AircraftDB`** — loads `lib/flightaware-*.csv` into memory. CSV format: `hexCode,tailNumber,aircraftType,aircraftCode`. `getMappings(hexCode)` returns a 4-tuple; indices 2 and 3 are aircraft type and description code.
- **`JsonFileHandler`** — `watchdog.FileSystemEventHandler` subclass. Listens for `on_created` events (readsb atomically replaces the file), validates the `now`/`messages`/`aircraft` keys, then calls the `newMessages` callback with the parsed dict.
- **`BaseMqtt`** — wraps `paho-mqtt`. `publishJson()` accepts either a string or a serializable object and returns `MQTTMessageInfo` for optional `.wait_for_publish()`.

#### MQTT topics (`AdsbMqtt`)

| Message type | Topic | Retained |
|---|---|---|
| Service discovery | `homeassistant/binary_sensor/adsb_monitor/status/config` | Yes |
| Service state | `adsb/monitor/status` | Yes |
| Track discovery | `homeassistant/sensor/adsb_<hexId>/config` | Yes |
| Track state | `adsb/vehicles/<hexId>/state` | No |
| Track count | `adsb/monitor/count` | Yes |
| Tracking count | `adsb/monitor/tracking` | Yes |

Removing a track sends an empty string to its discovery topic (un-registers it from HA). There is a 100ms `threading.Timer` delay between publishing a new track's discovery message and its first state update, to allow HA to register the entity first.

#### Hex ID normalization

ICAO hex IDs starting with `~` (MLAT-derived) are prefixed with `_` instead (MQTT topic-safe): `~abc123` → `_abc123`.
