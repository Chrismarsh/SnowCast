################################################
# Paths
################################################
#netcdf_file  = '/media/data3/nicway/GEM/Nov2014/1km/netcdf/GEM_1km_Nov_2014_Storm.nc'
netcdf_file  = '/media/data3/nicway/GEM/Nov2014/250m/netcdf/GEM_250m_Nov_2014_Storm.nc'


# Dir where output ascii files should go
#ascii_dir    = '/media/data3/nicway/GEM/Nov2014/1km/chm'
ascii_dir    = '/media/data3/nicway/GEM/Nov2014/250m/chm'


#########################################

# Name for output .json file containing metadata for forcing files
Forcing_config_file = 'GEM_250m_forcing.json'

# Offset from UTM to local time (i.e. Mountain standard time = -7)
# CHM forcing files will be in this time zone
local_time_offset = 0

# Coordinate system for output CHM files
coordsystem = 'geo' # 'geo' = geographic, 'pro' = projected
utm_zone = 11 # Only used if coordsystem='pro'

#### [min,max] extents for bounding box of latitude and longitude

# Fortress only
lat_r = [50.793,50.865]
lon_r = [-115.261,-115.161]


