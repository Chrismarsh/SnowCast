#!/bin/bash

# Calls 1) Downloader script, 2) Compiles geoTiff images into a netcdf format

# 1) Download Recent Landsat-8, Sentinel-2, and MODIS imagery
/home/nwayand/custom/anaconda2/bin/python Download_Recent_Landsat8_Sentinel2.py

# 2) Merge geoTIFF images into one netcdf file
/home/nwayand/custom/anaconda2/envs/NEW_rasterio/bin/python remote_tifs_to_netcdf.py

echo "Done Processing Remote Imagery."

