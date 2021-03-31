#!/bin/bash

# Stop of get any simple error
set -e

# This is needed because crontab does not have same env variables are user
PATH=$PATH:/home/nwayand/custom/anaconda2:/home/nwayand/custom/anaconda2/bin:/home/nwayand/custom/anaconda2/bin

# Timer
start=$SECONDS

## Script paths
# Where scripts are located
ex_dir=/home/nwayand/SnowCast/NWP_Forcing/
# CHM run dir
CHM_dir=/home/nwayand/snow_models/output_CHM/SnowCast/CHM_Configs/
# Config file to use
#Configfile=Config_GEM_west_fortress.py
Configfile=Configs/Config_GDPS_append.py

# Download GEM forecast
echo Downloading GEM
/home/nwayand/custom/anaconda2/bin/python $ex_dir"Download/Download_GDPS_GRIB2.py"  $ex_dir$Configfile

# Subset grib2 files (global) to Canada
echo Subsetting GDPS grib2 files
/home/nwayand/SnowCast/NWP_Forcing/Util/sub_set_grib2_files.sh /media/data3/nicway/GEM/GDPS/grib2_current

# Format grib2 to netcdf
echo Formating grib2 to netcdf
/home/nwayand/custom/anaconda2/envs/pynio/bin/python $ex_dir"GRIB2_to_NETCDF/GRIB2_GDPS_to_Netcdf.py" $ex_dir$Configfile

# Convert archived netcdf to CHM forcing
echo NETCDF to CHM ASCII Forcing
/home/nwayand/custom/anaconda2/bin/python  $ex_dir"NETCDF_to_CHM_ASCII/Netcdf_Day_Chunk_to_CHM_forcing_GDPS.py" $ex_dir$Configfile
##/home/nwayand/custom/anaconda2/bin/python  $ex_dir"Netcdf_Day_Chunk_to_CHM_forcing.py" $ex_dir$Configfile
##/home/nwayand/custom/anaconda2/bin/python $ex_dir"Netcdf_to_CHM_forcing.py" $ex_dir$Configfile

# Run CHM for available forcing period
$CHM_dir"Run_GDPS_CHM_Current.sh"

duration=$(( SECONDS - start ))
echo Took $duration seconds

