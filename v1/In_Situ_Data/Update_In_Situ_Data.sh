#!/bin/bash

# Stop of get any simple error
set -e

# This is needed because crontab does not have same env variables are user
PATH=$PATH:/home/nwayand/custom/anaconda2:/home/nwayand/custom/anaconda2/bin:/home/nwayand/custom/anaconda2/bin

## START USER CONFIG ##
# Where scripts are located
git_dir=/home/nwayand/SnowCast/
sub_dir=$git_dir/In_Situ_Data/
# Python executable
python_bin=/home/nwayand/custom/anaconda2/bin/python
# R executable
r_bin=/usr/bin/Rscript
# Options
updateHist=true # Updates historical data if true
## End USER CONFIG ##

# Timer
start=$SECONDS

# NRT download script folder
NRT_dir=Near_Real_Time_download/
# NRT download script folder
HIST_dir=Historical_download/
# Merged dir
MRG_dir=Merge_Network_scripts/
# QC dir
QC_dir=QC_Merged_file/

# Config file to use
Configfile=Path_Config.py

# Updating Recent data
# These execute in parallel
echo Updating Recent data
$python_bin $sub_dir$NRT_dir"NRT_AB_SWE_SD_to_netcdf.py"  $git_dir$Configfile &
$python_bin $sub_dir$NRT_dir"NRT_BC_Pillows_to_netcdf.py"  $git_dir$Configfile &
$python_bin $sub_dir$NRT_dir"NRT_recent_AB_Pillows_to_netcdf.py"  $git_dir$Configfile &
$r_bin $sub_dir$NRT_dir"Download_Wiksi_Data_to_csv.R"  # Important this finished before next line executes
$python_bin $sub_dir$NRT_dir"Merge_Wiski_ascii_to_netcdf.py" $git_dir$Configfile &

# Importing Historical data (static)
# These execute in parallel
if [ "$updateHist" = true ] ; then
    echo Updating Historical data
    $python_bin $sub_dir$HIST_dir"ABE_AGG_Historical_to_netcdf.py"  $git_dir$Configfile &
    $python_bin $sub_dir$HIST_dir"EC_SnowCourse_to_netcdf.py"  $git_dir$Configfile &
    $python_bin $sub_dir$HIST_dir"HIST_BC_Pillows_to_netcdf.py"  $git_dir$Configfile &
fi

# Wait until all above are done
wait

# Merging all data together
# These execute in serial
echo Merging all data
$python_bin $sub_dir$MRG_dir"Merge_Hourly_Network_data.py"  $git_dir$Configfile

# Quality controlling merged data
# These execute in serial
echo Quality controlling merged data
$python_bin $sub_dir$QC_dir"QC_Hourly_Merged_file.py"  $git_dir$Configfile

duration=$(( SECONDS - start ))
echo Took $duration seconds
