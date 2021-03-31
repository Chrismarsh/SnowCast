#!/bin/bash
OMP_NUM_THREADS=12
# Stop of get any simple error
set -e

# Run info
cd /home/nwayand/snow_models/output_CHM/SnowCast/CHM_Configs

./CHM -f HRDPS_CHM_Historical.json

# Process CHM point out
/home/nwayand/custom/anaconda2/bin/python /home/nwayand/SnowCast/Post_Processing/Point_Evals/CHM_point_output_to_netcdf.py ../Path_Config.py HRDPS_Historical

# Point plots
/home/nwayand/custom/anaconda2/bin/python /home/nwayand/SnowCast/Post_Processing/Point_Evals/Eval_CHM_to_stations_Historical.py ../Path_Config.py HRDPS_Historical

# Run plotting scripts
#echo "Running Plotting scripts"
#/home/nwayand/custom/anaconda2/bin/python /home/nwayand/SnowCast/Post_Processing/plot_scripts/Plot_SnowCast.py ../Path_Config.py HRDPS_Historical

echo "Uploading to server"
/home/nwayand/SnowCast/Web_Upload/Static_Figure_upload.sh

echo DONE!!!


