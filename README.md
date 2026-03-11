# ADSBMonitor
Tool for logging and analyzing ADS-B data

**WIP**

## Hardware
* Raspberry Pi 4B
* Flight Aware SDR USB dongle
* ???? SDR USB dongle
* ???? splitter
* ???? dual band (1090MHz and 978MHz) ?db antenna

## Software
* dump1090-fa: ?
* dump978-fa: ?
* readsb: ?
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
* use debian13 until the dump1090-fa repo has a version for trixie
* temporarily add repo to apt sources
'''
sudo wget -O /etc/apt/sources.list.d/abcd567a.list https://abcd567a.github.io/debian13/abcd567a.list
sudo wget -O /etc/apt/keyrings/abcd567a-key.gpg https://abcd567a.github.io/debian13/KEY2.gpg
sudo apt update
'''
* install packages
'''
sudo apt install piaware
sudo apt install dump1090-fa 
sudo apt install piaware-web
sudo apt install dump978-fa
sudo piaware-config uat-receiver-type sdr 
'''
* install readsb (to write '/run/readsb/aircraft.json')
'''
sudo bash -c "$(wget -nv -O - https://github.com/wiedehopf/adsb-scripts/raw/master/readsb-install.sh)"
sudo reboot
'''
  - configure by editing '/etc/default/readsb'
    * RECEIVER_OPTIONS
      - --lat=37.4599669
      - --lon=-122.1652244
    * DECODER_OPTIONS
      - --max-range=64
    * NET_OPTION
      - --net-api-port 8042
  - alternatively, set location with: 'sudo readsb-set-location 37.4599669 -122.1652244'
* remove repo when official dump1090-fa is released for Trixie
'''
sudo rm /etc/apt/sources.list.d/abcd567a.list
sudo apt update
'''

### Configure Applications

#### dump1090-fa

* configure the service
  - edit (as root) '/etc/default/dump1090-fa'
    * RECEIVER_LAT=37.4599669
    * RECEIVER_LON=-122.1652244
      - @37.4599669,-122.1652244,18.58
    * MAX_RANGE=48  # in NM
    * JSON_LOCATION_ACCURACY=2

????
    * envvars used by start script
      - RECEIVER_OPTIONS="--device-index 00001090 --gain -10 --ppm 0"
        * gain=-10: means use AGC
        * ppm=0: ????
      - NET_OPTIONS="--net --net-http-port 8080 --net-ro-port 30002 --net-beast 30005"
        * net: enable TCP output
        * net-http-port: web/JSON listen port
        * net-ro-port: raw output listen port
        * net-beast: Beast-format output (used by other feeders)
      - JSON_OPTIONS="--json-location-accuracy 2"
        * json-location-accuracy: digits of precision
      - DECODER_OPTIONS: rarely changed

* set up systemd
  - create (as root) '/etc/systemd/system/dump1090-fa.service'
'''
[Unit]
Description=dump1090-fa
After=network.target

[Service]
ExecStart=/usr/bin/dump1090-fa --device-index 00001090 --net --quiet
Restart=always
User=jdn
Group=plugdev

[Install]
WantedBy=multi-user.target
'''

* enable the service
'''
sudo systemctl daemon-reload
sudo systemctl enable --now dump1090-fa
'''

* tar1090: enhanced map
  - https://github.com/wiedehopf/tar1090
  - install
    * sudo bash -c "$(wget -nv -O - https://github.com/wiedehopf/tar1090/raw/master/install.sh)"
  - configure (to enable UAT978)
    * 'sudo ex /etc/default/tar1090'
    * 'sudo systemctl restart tar1090'
  - update
    * sudo bash -c "$(wget -nv -O - https://github.com/wiedehopf/tar1090/raw/master/install.sh)"
    * configuration should be preserved

#### dump978-fa

## Operation

* run tar1090
  - 'http://adsbrx.lan/tar1090'
  - 'http://adsbrx.lan/tar1090?pTracks'



## Notes
* dump1090-fa is the popular fork (https://github.com/flightaware/dump1090)
  - it runs on bookworm, but has issues with python watchdog and json
  - there are builds for trixie
* Trixie installs
  --> be prepared for dump1090-fa to make an official release for Trixie
  - debian13: 
    * https://github.com/abcd567a/debian13/tree/master
    * https://github.com/abcd567a/debian13/blob/master/README.md
* 

