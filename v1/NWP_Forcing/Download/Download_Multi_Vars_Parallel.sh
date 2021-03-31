#!/bin/bash

declare -a arr=("TMP:2 m" "RH:2 m" "UGRD:10 m" "VGRD:10 m" "PRATE" "CPOFP" "DSWRF" "DLWRF" "PRES:surface" "WEASD" "SNOD" "APCP:surface")

for i in "${arr[@]}"
do
    echo "$i"
    python Download_HRRR.py ../Configs/Config_HRRR.py $i &    
   # or do whatever with individual element of the array
done

echo Finished Download of HRRR data.
