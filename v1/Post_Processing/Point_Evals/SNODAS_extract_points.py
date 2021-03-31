import xarray as xr
import numpy as np
import os
import sys
import imp
import glob
import time

''' Extracts SNODAS modeled values at observational points. Exports to netcdf file'''

# Make dictionary of obs:model variable names to compare
# model:obs
vars_all = {'AirtemperatureA': 't', 'AirMoistureContentA': 'rh', 'IncrementalPrecipitationA': 'p',
            'ScalarWindSpeedA': 'U_2m_above_srf', 'DownwardSolarRadiation': 'iswr', 'DownwardTerrestrialRad': 'ilwr',
            'UpwardTerrestrialRad': 'ilwr_out',
            'SnowWaterEquivelentA': 'swe', 'SnowDepthA': 'snowdepthavg', 'WindDirectionatA': 'vw_dir',
            'Time_UTC': 'time', 'staID': 'station'}

plot_key = {'ilwr_out': 'Outgoing Longwave', 'T_s_0': 'Surface temperature', 't': 'Air Temperature',
            'rh': 'Relative Humidity',
            'p': 'Precipitation', 'ilwr': 'Incoming Longwave', 'iswr': 'Shortwave Radiation',
            'U_2m_above_srf': 'Wind Speed', 'vw_dir': 'Wind Direction', 'swe': 'Snow Water Equivalent',
            'snowdepthavg': 'Snowdepth'}

ylabel_unit = {'ilwr_out': 'W m-2', 'G': 'W m-2', 'T_s_0': 'C', 't': 'C', 'rh': '%', 'p': 'm', 'ilwr': 'W m-2',
               'iswr': 'W m-2',
               'U_2m_above_srf': 'm/s', 'vw_dir': 'degrees true north', 'swe': 'm', 'snowdepthavg': 'm'}

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) != 3:
    sys.exit('Requires two arguments [configuration-file example CHM run (for points)]')

# Get name of configuration file/module
configfile = sys.argv[1]
chm_run_dir = sys.argv[2]

# Load in configuration file as module
X = imp.load_source('', configfile)

# Assign to local variables
data_dir = X.data_dir
git_dir = X.git_dir
#
# # Load in OBS
# file_in = os.path.join(data_dir, 'QC', 'Hourly_QC.nc')  # CRHO and other data
# ds_obs = xr.open_dataset(file_in, engine='netcdf4')
# # Rename obs variable names to model variable names
# ds_obs.rename(vars_all, inplace=True);
# # print(ds_obs)
#
# # Load CHM point output, to get lat long for points to extract from SNODAS
# chm_file = os.path.join(git_dir, 'CHM_Configs', chm_run_dir, 'points','CHM_pts.nc')
# ds_chm = xr.open_dataset(chm_file)
# # add lat and lon from OBS file
# ds_chm.coord['lat'] = ds_obs.sel(station=ds_chm.station).Lat
# print(ds_chm)

# Load in model output points file
pts_file = os.path.join(git_dir, 'CHM_Configs','SnowCast_stations.json')
import json
pts_dict = json.load(open(pts_file))
pts_lat = [value['latitude'] for (key, value) in pts_dict.iteritems()]
pts_lon = [value['longitude'] for (key, value) in pts_dict.iteritems()]
pts_sta = [key for (key, value) in pts_dict.iteritems()]

# Load in SNODAS data
snodas_dir = r'/media/data3/nicway/python/NOHRSC_SNODAS'
nc_dir = os.path.join(snodas_dir,'download_data','nc')
ds_snodas_swe = xr.open_mfdataset(nc_dir+'/*SWE*sub*.nc')
# print(ds_snodas_swe)
ds_snodas_SD = xr.open_mfdataset(nc_dir+'/*SNWZ*sub*.nc')
# Merge snodas vars
ds_snodas = xr.merge([ds_snodas_swe, ds_snodas_SD])

# Extract nearest snodas cell values
tol = np.abs(np.nanmean(np.diff(ds_snodas.lon.values))) # On grid cell width
pts_snodas = ds_snodas.sel_points(dim=pts_sta, lon=pts_lon, lat=pts_lat,
                               method='nearest', tolerance=tol).rename({'points':'station'});

# Option to remove unicode
# pts_snodas['station'] = [x.encode('ascii','ignore') for x in pts_snodas['station'].values]

# Store in new netcdf
nc_file_out = os.path.join(snodas_dir,'points','Snodas_Snowcast_pts.nc')
pts_snodas.to_netcdf(nc_file_out)

# Plot to check
pts_snodas.SWE.plot()
