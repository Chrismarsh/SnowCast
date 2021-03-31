#!/bin/bash

# Uses wgrib2 to subset all .grib2 files within input dir
# Using the hardcoded lat/lon bounds below

grib2_dir=$1 # Path to folder containing grib2 files

cd $grib2_dir

shopt -s nullglob # Ignore no matches case
for f in *.grib2; do
    # Get file namebase
    filename="${f%.*}"
    # Subset
    /home/nwayand/custom/wgrib2/wgrib2 $f -small_grib -144.72657:-48.457035 40.794405:71.5921 $filename"_SUB.grib2"  
    # Clean up
    rm $f 
done

echo "Done Subsetting grib2 files"

