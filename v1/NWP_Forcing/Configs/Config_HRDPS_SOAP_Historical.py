################################################
# Paths
################################################

# Dir where output netcdf files go
netcdf_dir  = '/media/data3/nicway/GEM/archive/SOAP/netcdf'

# Dir where output ascii files should go
ascii_dir    = '/media/data3/nicway/GEM/archive/SOAP/ascii_HRDPS_SnowCast_full'

# File that contains the elevation (height)
hgt_file = '/media/data3/nicway/GEM/archive/SOAP/kananaskis_SHRPD_HRPDS_2.5km_2014_11_UTC_HGT_SFC.nc'

# Dictionary list to change GEM variables names into CHM required names
var_dic = {'WIND_40maboveground':'u','WDIR_40maboveground':'vw_dir','TMP_2maboveground':'t','DLWRF_surface':'Qli','DSWRF_surface':'Qsi','PRES_surface':'press'}

#########################################
# Configuration for Netcdf_to_CHM.py
#########################################

# Name for output .json file containing metadata for forcing files
Forcing_config_file = 'SOAP_forcing.json'

# Offset from UTM to local time (i.e. Mountain standard time = -7)
# CHM forcing files will be in this time zone
local_time_offset = 0

# Coordinate system for output CHM files
coordsystem = 'geo' # 'geo' = geographic, 'pro' = projected
#utm_zone = 11 # Only used if coordsystem='pro'

#### [min,max] extents for bounding box of latitude and longitude

# Testing (1 grid cell)
#lat_r = [50.500751344760,50.530751344763]
#lon_r = [-115.78881097936,-115.78881097933]

## Fortress only domain
#lat_r = [50.793,50.865]
#lon_r = [-115.261,-115.161]

## Fortress with buffer
#lat_r = [50.632,51.006]
#lon_r = [-115.445,-115.026]

# Marmot
#lat_r = [50.93834,50.978118]
#lon_r = [-115.23295870271967,-115.130036455333]

# Bow river basin
#lat_r = [50.411581,51.218712]
#lon_r = [-115.793152,-114.362183]

# CRHO (crho_extent.tif)
lat_r = [50.66,51.7933333333333]
lon_r = [-116.645,-114.769166666667]

# Entire GEM west domain
#lat_r = [0,90]
#lon_r = [-180,180]

