################################################
# Paths
################################################
# Dir to put GEM grib2 files
download_dir = '/media/data3/nicway/GEM/GDPS/grib2_current'
# download_dir = '/media/data3/nicway/GEM/GDPS/grib2_test'

# Dir where output netcdf files go
netcdf_dir  = '/media/data3/nicway/GEM/GDPS/netcdf_archive'

# Dir where output ascii files should go
ascii_dir    = '/media/data3/nicway/GEM/GDPS/CHM_archive_append'

################################################
# Configuration for Download_HRDPS_GRIB2.py
################################################

# Forecast initializatio time (UTM)
# Options are: '00','06','12','18'
Init_H   = '00'

domain = '25km'

# Define HRDPS variables to download (names match file names in HRDPS system)
#Variable   = ['TMP_ISBL_1015','TMP_ISBL_1000','TMP_ISBL_0985','TMP_ISBL_0970','TMP_ISBL_0950','TMP_ISBL_0925',
#'TMP_ISBL_0900','HGT_ISBL_1015','HGT_ISBL_1000','HGT_ISBL_0985','HGT_ISBL_0970','HGT_ISBL_0950','HGT_ISBL_0925','HGT_ISBL_0900',
#'HGT_SFC_0','TMP_TGL_2','RH_TGL_2','WIND_TGL_10','WDIR_TGL_10','PRES_SFC_0','DLWRF_SFC_0','DSWRF_SFC_0','PRATE_SFC_0',
#'WEASN_SFC_0','WEARN_SFC_0','WEAPE_SFC_0','WEAFR_SFC_0','LHTFL_SFC_0','SHTFL_SFC_0','ALBDO_SFC_0']

Variable = ['TMP_ISBL_1015','TMP_ISBL_1000','TMP_ISBL_985','TMP_ISBL_970','TMP_ISBL_950','TMP_ISBL_925','TMP_ISBL_900','HGT_ISBL_1015','HGT_ISBL_1000','HGT_ISBL_985','HGT_ISBL_970','HGT_ISBL_950','HGT_ISBL_925','HGT_ISBL_900','TMP_TGL_2','SPFH_SFC_0','WIND_TGL_10','WIND_TGL_40','WDIR_TGL_10','WDIR_TGL_40','PRES_SFC_0','DLWRF_SFC_0','DSWRF_SFC_0','PRATE_SFC_0','WEASN_SFC_0','WEARN_SFC_0','WEAPE_SFC_0','WEAFR_SFC_0','LHTFL_SFC_0','SHTFL_SFC_0','ALBDO_SFC_0']

##########################################
#Configuration for GRIB2_to_Netcdf.py
##########################################
# 'RH_P0_L103_GLL0':'rh'
# Dictionary list to change GEM variables names into CHM required names (Names match internal variable names within grib files (note: they don't match above Variable names!))
var_dic = {'time':'datetime','TMP_P0_L103_GLL0':'t','WDIR_P0_L103_GLL0':'vw_dir','WIND_P0_L103_GLL0':'u','DLWRF_P8_L1_GLL0_acc':'Qli','DSWRF_P8_L1_GLL0_acc':'Qsi','PRATE_P0_L1_GLL0':'p','PRES_P0_L1_GLL0':'press','RPRATE_P8_L1_GLL0_acc':'p_rain','SPRATE_P8_L1_GLL0_acc':'p_snow','FPRATE_P8_L1_GLL0_acc':'p_frz_rain','IPRATE_P8_L1_GLL0_acc':'p_ice_pellet','ALBDO_P0_L1_GLL0':'albedo','LHTFL_P0_L1_GLL0':'latentHeat','SHTFL_P0_L1_GLL0':'sensibleHeat'}

#########################################
# Configuration for Netcdf_to_CHM.py
#########################################

# Name for output .json file containing metadata for forcing files
Forcing_config_file = 'GEM_forcing.json'

# Offset from UTM to local time (i.e. Mountain standard time = -7)
# CHM forcing files will be in this time zone
local_time_offset = 0

# Coordinate system for output CHM files
coordsystem = 'geo' # 'geo' = geographic, 'pro' = projected
utm_zone = 11 # Only used if coordsystem='pro'

#### [min,max] extents for bounding box of latitude and longitude

# Bow river basin
#lat_r = [50.411581,51.218712]
#lon_r = [-115.793152,-114.362183]

# CRHO (crho_extent.tif)
lat_r = [50.66,51.7933333333333]
lon_r = [-116.645,-114.769166666667]


# Entire GEM west domain
#lat_r = [0,90]
#lon_r = [-180,180]

