import glob
import imp
import numpy as np
import os
import pandas as pd
import sys
import time
import xarray as xr

import CHM_functions as chmF

''' Evaluate GEM forecasts of meteorology compared to point observations.
    Calculate variable X error versus lead time (1-48, or 1-(6day) ). '''

# Make dictionary of obs:model variable names to compare
# model:obs
vars_all = {'AirtemperatureA':'t','AirMoistureContentA':'rh','IncrementalPrecipitationA':'p',
            'ScalarWindSpeedA':'U_2m_above_srf','DownwardSolarRadiation':'iswr','DownwardTerrestrialRad':'ilwr',
            'UpwardTerrestrialRad':'ilwr_out',
            'SnowWaterEquivelentA':'swe','SnowDepthA':'snowdepthavg','WindDirectionatA':'vw_dir',
           'Time_UTC':'time','staID':'station'}

plot_key = {'ilwr_out':'Outgoing Longwave','T_s_0':'Surface temperature','t':'Air Temperature','rh':'Relative Humidity',
            'p':'Precipitation','ilwr':'Incoming Longwave','iswr':'Shortwave Radiation',
            'U_2m_above_srf':'Wind Speed','vw_dir':'Wind Direction','swe':'Snow Water Equivalent','snowdepthavg':'Snowdepth'}

ylabel_unit = {'ilwr_out':'W m-2','G':'W m-2','T_s_0':'C','t':'C','rh':'%','p':'m','ilwr':'W m-2','iswr':'W m-2',
            'U_2m_above_srf':'m/s','vw_dir':'degrees true north','swe':'m','snowdepthavg':'m'}
#


# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) != 2:
    sys.exit('Requires one arguments [configuration file]')

# Get name of configuration file/module
configfile = sys.argv[1]

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
data_dir = X.data_dir

# Load in OBS
file_in = os.path.join(data_dir, 'QC', 'Hourly_QC.nc') # CRHO and other data
OBS_data = xr.open_dataset(file_in, engine='netcdf4')
# Rename obs variable names to model variable names
OBS_data.rename(vars_all, inplace=True);

# TODO: remove hard coded paths
HRDPS = False
GDPS = True
# GEM data
if HRDPS:
    gem_nc_dir = r'/media/data3/nicway/GEM/west/netcdf_archive'
    gem_file_out = r'/media/data3/nicway/SnowCast/GEM_eval/hrdps.nc'
    obs_file_out = r'/media/data3/nicway/SnowCast/GEM_eval/hrdps_obs.nc'
elif GDPS:
    gem_nc_dir = r'/media/data3/nicway/GEM/GDPS/netcdf_archive'
    gem_file_out = r'/media/data3/nicway/SnowCast/GEM_eval/gdps.nc'
    obs_file_out = r'/media/data3/nicway/SnowCast/GEM_eval/gdps_obs.nc'

# Move to input
os.chdir(gem_nc_dir)

# Get all file names
all_files =  glob.glob('*.nc')

# Sort file names (open_mfdataset _should_ handle this, but this is a hack to put in correct order)
all_files = sorted(all_files)

# Define naive_fast that searches for the nearest WRF grid cell center
def naive_fast(latvar,lonvar,lat0,lon0):
    # Read latitude and longitude from file into numpy arrays
    latvals = latvar[:]
    lonvals = lonvar[:]
    dist_sq = (latvals-lat0)**2 + (lonvals-lon0)**2
    minindex_flattened = dist_sq.argmin()  # 1D index of min element
    iy_min,ix_min = np.unravel_index(minindex_flattened, latvals.shape)
    return iy_min,ix_min

# HRDPS is on a rotated grid, so below finds indices of nearest OBS points
if HRDPS:
    # Get indices of nearest OBS stations
    ds_grid = xr.open_dataset(all_files[0])
    ds_grid = ds_grid[['gridlat_0','gridlon_0','HGT_P0_L1_GST0']]
    gem_x = []
    gem_y = []
    for csta in OBS_data.station:
        clat = OBS_data.Lat.sel(station=csta).values
        clon = OBS_data.Lon.sel(station=csta).values
        (c_y, c_x) = naive_fast(ds_grid.gridlat_0.values, ds_grid.gridlon_0.values, clat, clon)
        gem_x.append(c_x)
        gem_y.append(c_y)

# (Optional) restrict by extent (i.e. Snowcast)

# For each forecast file
gem_list = []
obs_list = []
for cf in all_files:
    print(cf)

    t = time.time()
    # Load in file
    ds = xr.open_dataset(cf).load()
    ds.rename({'datetime':'time','u':'U_2m_above_srf','Qsi':'iswr','Qli':'ilwr'}, inplace=True)
    c_init_time = ds.isel(time=0).time.values

    # Select by nearest OBS points
    if HRDPS:
        ds_pts = ds.sel_points(dim='station', xgrid_0=gem_x, ygrid_0=gem_y)
    elif GDPS:
        ds_pts = ds.sel_points(dim='station', lat_0=OBS_data.Lat, lon_0=OBS_data.Lon, method='nearest')
    ds_pts['station'] = OBS_data.station.copy(deep=True)
    ds = None

    # If the forecast download failed and was missing, we had to fill it,
    # which created extra xgrid_0 and ygrid_0 dims
    if 'xgrid_0' in ds_pts:
        print("Dropped xgrid_0... from ",cf)
        ds_pts = ds_pts.drop(['xgrid_0','ygrid_0'])

    try:
        c_obs = OBS_data.sel(station=ds_pts.station, time=ds_pts.time).load()
    except:
        print("No obs found, skipping.")
        continue
    #print(c_obs)

    # Store as forecast hours
    ds_pts.rename({'time':'forecastHour'}, inplace=True)
    ds_pts['forecastHour'] = np.arange(0,len(ds_pts.forecastHour))
    ds_pts.coords['initDate'] = c_init_time
    c_obs.rename({'time':'forecastHour'}, inplace=True)
    c_obs['forecastHour'] = np.arange(0,len(c_obs.forecastHour))
    c_obs.coords['initDate'] = c_init_time
    #print(c_obs)

    gem_list.append(ds_pts)
    obs_list.append(c_obs)
    elapsed = time.time() - t
    print(elapsed)
    
# Merge
print("merging by initialization")
gem_mrg = xr.concat(gem_list, dim='initDate')
obs_mrg = xr.concat(obs_list, dim='initDate')

print(gem_mrg)
print(obs_mrg)

# Save to netcdf files
gem_mrg.to_netcdf(gem_file_out)
obs_mrg.to_netcdf(obs_file_out)



