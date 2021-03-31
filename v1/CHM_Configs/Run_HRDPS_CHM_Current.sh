#!/bin/bash

# Threads for CHM
OMP_NUM_THREADS=5

# Source config options
. chm_run_configs.txt

failfunction()
{
    if [ "$1" != 0 ]
    then echo "One of the commands has failed! Mailing for help."
         mail -s "CHM Run HRDPS_Current Failed." $SNOWCASTEMAIL <<< "CHM Run HRDPS_Current Failed."
         exit
    fi
}

# Testing failfunction
#cd missingdir
#failfunction "$?"

# Caller script to run CHM for all GEM hours
#N_threads=10 # number of threads to use for vtu2geo parallel

# Run info
cd /home/nwayand/snow_models/output_CHM/SnowCast/CHM_Configs

./CHM -f HRDPS_CHM_Current.json
failfunction "$?"

# Process CHM point out
/home/nwayand/custom/anaconda2/bin/python /home/nwayand/SnowCast/Post_Processing/Point_Evals/CHM_point_output_to_netcdf.py ../Path_Config.py forecast_CRHO_spinup
failfunction "$?"

# Point plots
/home/nwayand/custom/anaconda2/bin/python /home/nwayand/SnowCast/Post_Processing/Point_Evals/Eval_CHM_to_stations_Historical.py ../Path_Config.py forecast_CRHO_spinup
failfunction "$?"

# Run plotting scripts
echo "Running Plotting scripts"
/home/nwayand/custom/anaconda2/bin/python /home/nwayand/SnowCast/Post_Processing/plot_scripts/Plot_SnowCast.py ../Path_Config.py forecast_CRHO_spinup
failfunction "$?"
echo "Plotting complete"


# Making GIFS
../Post_Processing/GIFS/png_to_gif.sh /home/nwayand/SnowCast/CHM_Configs/forecast_CRHO_spinup/figures/snowdepthavg
failfunction "$?"
../Post_Processing/GIFS/png_to_gif.sh /home/nwayand/SnowCast/CHM_Configs/forecast_CRHO_spinup/figures/swe
failfunction "$?"

# Upload to server
# TODO: build into python plotting scripts like this (http://stackoverflow.com/questions/12613797/python-script-uploading-files-via-ftp)
echo "Uploading to server"
/home/nwayand/SnowCast/Web_Upload/Static_Figure_upload.sh
failfunction "$?"
echo DONE!!!


