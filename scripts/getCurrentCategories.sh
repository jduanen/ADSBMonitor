jdn@gpuServer1:~/Code/ADSBMonitor/scripts$ head printRetainedMsgs.sh 
#!/bin/bash
#
# Script to print the categories of vehicles currently within the tracking volume

curl -s "http://adsbrx.lan:8042/?all" | jq '.aircraft[].category' | sort | uniq | sed -e 's/^null$//'
