'''
Plot point and gridded observations
'''
import cartopy.crs as ccrs
import datetime
import imp
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
import seaborn as sns
import sys
import time
import xarray as xr
from scipy.interpolate import griddata

start_time = time.time()
# Hack to force datetimes to display in GMT/UTC (numpy 1.11.1 has fixed this but other dependent modules (pynio) can't handel numpy 1.11.1)
os.environ['TZ'] = 'GMT'
time.tzset()

# General plotting settings
sns.set_style('whitegrid')
sns.set_context("talk", font_scale=1.5, rc={"lines.linewidth": 2.5})
fig_res = 90 # dpi

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) != 2:
    sys.exit('Requires 1 argument [configuration file] ')

# Get name of configuration file/module
configfile = sys.argv[1]
# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
data_dir = X.data_dir
git_dir = X.git_dir

# Target GEM files
gem_run = 'Historical'
# gem_run = 'Current'

# Load in Gridded Obs file
obs_file = os.path.join(data_dir, 'QC', gem_run+'_Gridded.nc')
ds_grid = xr.open_dataset(obs_file).IncrementalPrecipitationA

# Load in Observations
obs_file = os.path.join(data_dir, 'QC', 'Hourly_QC.nc')
ds_pts = xr.open_dataset(obs_file).IncrementalPrecipitationA


# Make plot of observations per water year
# plt.figure()


tS = datetime.datetime(2014,10,1)
# tE = datetime.datetime(2014,10,15)
tE = datetime.datetime(2015,9,30)
ds_grid_sel = ds_grid.sel(Time_UTC=slice(tS,tE))
ds_pts_sel = ds_pts.sel(Time_UTC=slice(tS,tE))

# Trim to CRHO domain
lat_r = [50.66,51.7933333333333]
lon_r = [-116.645,-114.769166666667]
# Trim stations to domain of interest (allow some padding to included
# stations around boarder
bdy = 0.2 # degrees boundary
ds_pts_sel = ds_pts_sel.where((ds_pts_sel.Lat>lat_r[0]-bdy) & (ds_pts_sel.Lat<lat_r[1]+bdy) &
                      (ds_pts_sel.Lon>lon_r[0]-bdy) &
                  (ds_pts_sel.Lon<lon_r[1]+bdy), drop=True)

# Get sum for checking data QC
ds_pts_sum = ds_pts_sel.sum(dim='Time_UTC')

# Drop missing stations
ds_pts_sel = ds_pts_sel.where((ds_pts_sum!=0) & (ds_pts_sum.notnull()) &
                      (ds_pts_sel.Lon.notnull()) & (ds_pts_sel.Lat.notnull())
                      & (ds_pts_sel.Elevation.notnull()), drop=True)


plt.figure()
plt.plot(ds_pts_sel.Time_UTC.values,
         ds_pts_sel.cumsum(dim='Time_UTC').values)


''' Plot Station obs, interpolated station, Modeled values'''

# Plot contour the gridded data and points
p_colors = matplotlib.colors.ListedColormap(sns.color_palette("Reds", 12))
fig = plt.figure(figsize=(20, 12))
ax1 = plt.axes(projection=ccrs.AlbersEqualArea())
X = ds_grid_sel.sum(dim='Time_UTC', skipna=False)
import numpy.ma as ma
Zm = ma.masked_invalid(X.values)
plt.pcolormesh(X.gridlon_0, X.gridlat_0, Zm,
               cmap=p_colors,
               vmin=X.min(),
               vmax=X.max())
plt.colorbar()
# plot data points.
plt.scatter(ds_pts_sel.Lon.values,ds_pts_sel.Lat.values,marker='o',
            c='k',s=20, cmap=p_colors)
plt.scatter(ds_pts_sel.Lon.values,ds_pts_sel.Lat.values,marker='o',
            c=ds_pts_sel.sum(dim='Time_UTC').values,
            s=15, cmap=p_colors)

plt.show()