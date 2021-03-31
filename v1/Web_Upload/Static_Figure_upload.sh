#!/bin/bash

# Key/value array local dir name/remote dir name
declare -A arr=(["forecast_CRHO_spinup"]="HRDPS" ["GDPS_Current"]="GDPS" ["HRDPS_Historical"]="HRDPS_HIST" ["HRDPS_Current_BS"]="HRDPS_with_blowing_snow")

# Sync it
for key in ${!arr[@]}; do
    echo ""
    rsync -asv /home/nwayand/SnowCast/CHM_Configs/${key}/figures/* root@www.snowcast.ca:/var/www/html/static/${arr[${key}]}/
done

