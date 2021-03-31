#!/bin/bash
#set -e

# Converts grib2 files to netcdf using a subset of variables
# Note: source activate ncl (see ncl_conda_env.txt in this repo for install instructions)

source activate ncl

if [ $# -eq 0 ]
  then
    echo "No arguments supplied. One is required [path to HRR data containing grib2 folder]"
    exit 1
fi

# Dirs and options
base_dir=$1 # This should be the dir that contains grib2 and netcdf
folderin=$base_dir'/grib2' #folder where the grib are
folderout=$base_dir'/netcdf' #folder to store netcdf
## Extent to subset to
# Yakima
#subROI='-121.48187300000001:-120.336557 46.44775:47.01475'
# CRHO - SnowCast
subROI='-116.645:-114.769166666667 50.66:51.7933333333333'

# Keep list of error files
errFile=$base_dir'/grib2_error_files.txt'
rm -f $errFile # Remove it if it already exists

cd $folderin # cd to that folder

#now loop through all the grib files in there
shopt -s extglob
for f in HRRR*.grib2
do
    # Subset to region of interest
    filename=$(basename "$f")
    small_f="subROI_"$filename
    #echo $small_f
    wgrib2  $f -small_grib $subROI $small_f
    # Test if it failed
    response=$?
    if   [ $response -ne 0 ]; then
        echo "wgrib2 failed for some reason"
        echo $f >> $errFile
        # Remove bad subROI file if it exists
        rm -f $small_f
    fi
    # Clean up
    #rm -f $small_f
done

# Concatenate
echo "Starting concat"
#cat subROI_* > ../HRRR.grib2 # This fails for large number of files, hence the line below.
find -type f -name  'subROI_*' | xargs -n 32 -P 8 cat >> ../HRRR.grib2
echo "Finished concat"

# to netcdf
ncl_convert2nc ../HRRR.grib2 -o $folderout -itime # -th 2000
# Clean up
rm -f ../HRRR.grib2
echo "Finished converting to netcdf"



