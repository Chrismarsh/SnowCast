################################################
# Paths
################################################

# Dir where output netcdf files go
#netcdf_dir  = '/home/nwayand/WRF/data2/NOBACKUP/sak298/Post_processed/2000_1HR_2D'
netcdf_dir  = '/home/nwayand/WRF/home/new365/WRF_hist'

# Dir to file that contains constant WRF variables (lat/long/height)
netcdf_const_dir = '/home/nwayand/WRF/data2/NOBACKUP/sak298/Post_processed/4_bill/wrfout_d01_constant.nc'

# Dir where output ascii files should go
ascii_dir    = '/media/data2/WRF_hist/ascii_format_2001_2013'

# Dictionary list to change GEM variables names into CHM required names
var_dic = {'T2':'t','GLW':'Qli','SWDOWN':'Qsi','RAINNC':'p','PSFC':'press','ALBEDO':'albedo','LH':'latentHeat','HFX':'heatflux'}

#########################################
# Configuration for Netcdf_to_CHM.py
#########################################

# Name for output .json file containing metadata for forcing files
Forcing_config_file = 'WRF_forcing.json'

# Offset from UTM to local time (i.e. Mountain standard time = -7)
# CHM forcing files will be in this time zone
local_time_offset = 0

# Coordinate system for output CHM files
coordsystem = 'geo' # 'geo' = geographic, 'pro' = projected
utm_zone = 11 # Only used if coordsystem='pro'

#### [min,max] extents for bounding box of latitude and longitude

# Bow river basin
lat_r = [50.411581,51.218712]
lon_r = [-115.793152,-114.362183]

# Entire GEM west domain
#lat_r = [0,90]
#lon_r = [-180,180]

