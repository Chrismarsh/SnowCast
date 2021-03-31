################################################
# Paths
################################################

download_dir = '/media/data3/nicway/HRRR/SnowCast/grib2'

# Dir where output netcdf files go
#netcdf_dir  = '/media/data2/HRRR/yakima/netcdf'

# Dir where output ascii files should go
#ascii_dir    = '/media/data1/HRRR/yakima/ascii'

# File that contains the elevation (height)
hgt_file = '/media/data2/HRRR/yakima/HGT/subROI_HRRRfromPando_20170310_h00_f00_HGT_surface.nc'

# Dictionary list to change GEM variables names into CHM required names
var_dic = {'TMP_P0_L103_GLC0':'t','DLWRF_P0_L1_GLC0':'Qli','DSWRF_P0_L1_GLC0':'Qsi','PRES_P0_L1_GLC0':'press','RH_P0_L103_GLC0':'rh'}

# 'CPOFP_P0_L1_GLC0':'fraction_frozen'

#########################################
# Configuration for Netcdf_to_CHM.py
#########################################

# Name for output .json file containing metadata for forcing files
Forcing_config_file = 'yakima_forcing.json'

# Offset from UTM to local time (i.e. Mountain standard time = -7)
# CHM forcing files will be in this time zone
local_time_offset = 0

# Coordinate system for output CHM files
coordsystem = 'geo' # 'geo' = geographic, 'pro' = projected
#utm_zone = 11 # Only used if coordsystem='pro'

#### [min,max] extents for bounding box of latitude and longitude
# Entire GEM west domain
lat_r = [0,90]
lon_r = [-180,180]

