# ADSBMonitor
Tool for logging and analyzing ADS-B data

**WIP**

## TODO
  * put setup information for ADS-B server in here
  * on adsbrx.lan: install virtualenv, get pip, and install watchdog and mqtt packages
    - similar to birdpi.lan
  * figure out what the HA discovery message should look like
  * emit discovery message on startup
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

