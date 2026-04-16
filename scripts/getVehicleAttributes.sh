#!/bin/bash
#
# Script to get messages from the vehicles currently in the tracking volume
#  and extract and print the desired fields

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

${SCRIPT_DIR}/printInVolumeVehicles.sh | jq -r 'if type == "array" then .[]
   elif type == "object" then . 
   else empty end
| select(type == "object") 
| "\(.track_name // "") \(.hex // "") \(.s_dist // "") \(.category // "") \(.ac_type // "") \(.ac_desc // "") \(.alt // "") \(.gs // "") \(.track // "") \(.r_dir // "")"'
