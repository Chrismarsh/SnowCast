'''
Take netcdf file of observations of variable X, interpolate to a grid taken from a NWP model
'''
import PP
import datetime
import imp
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import numpy.ma as ma
import os
import pandas as pd
import seaborn as sns
import sys
import xarray as xr
from scipy.interpolate import griddata

import idw

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
git_dir   = X.git_dir

# Target GEM files
gem_run = 'Historical'
# gem_run = 'Current'

# Interpolated obs file out
nc_file_out = os.path.join(data_dir, 'QC', gem_run+'_Gridded.nc')

# Load in GEM model grid and point Observation data
if gem_run == 'Current':
    ds_gem = xr.open_dataset(r'/media/data3/nicway/GEM/west/netcdf_archive/GEM_2_5km_west_2017-03-27T01:00:00.000000000.nc')
    # Trim to one time step
    ds_gem = ds_gem.isel(datetime=0).drop('datetime')
elif gem_run == 'Historical':
    ds_gem = xr.open_dataset(r'/media/data3/nicway/GEM/archive/SOAP/netcdf/kananaskis_SHRPD_HRPDS_2.5km_2017_08_UTC_DLWRF_SFC.nc')
    # Hgt not included in GEM files so import here and merge later
    ds_hgt = xr.open_dataset(r'/media/data3/nicway/GEM/archive/SOAP/kananaskis_SHRPD_HRPDS_2.5km_2014_11_UTC_HGT_SFC.nc',
                             engine='netcdf4')
    # Drop time (same for all times)
    ds_hgt = ds_hgt.isel(time=0)
    ds_hgt = ds_hgt.rename({'HGT_surface':'HGT_P0_L1_GST0'});
    # Rename to common dim names
    ds_gem = ds_gem.rename({'time':'datetime',
                            'latitude':'gridlat_0',
                            'longitude':'gridlon_0'});
    # Trim to one time step
    ds_gem = ds_gem.isel(datetime=0).drop('datetime')
    ds_gem = xr.merge([ds_gem, ds_hgt])
    # Adjust longitude
    ds_gem['gridlon_0'] = ds_gem.gridlon_0 - 360
else:
    raise ValueError('gem_run not found.')

# Trim to CRHO domain
lat_r = [50.66,51.7933333333333]
lon_r = [-116.645,-114.769166666667]
bdy = 0.2 # degrees boundary
ds_gem = ds_gem.where((ds_gem.gridlat_0>lat_r[0]-bdy) &
                      (ds_gem.gridlat_0<lat_r[1]+bdy) &
                      (ds_gem.gridlon_0>lon_r[0]-bdy) &
                  (ds_gem.gridlon_0<lon_r[1]+bdy), drop=True)
print(ds_gem)

# Load in Observations
obs_file = os.path.join(data_dir, 'QC', 'Hourly_QC.nc')
ds_obs = xr.open_dataset(obs_file)
print(ds_obs)

cvar = 'IncrementalPrecipitationA'

# Get precipitation within time period of interest
sDate = datetime.datetime(2012, 10, 1)
eDate = datetime.datetime(2017, 9, 30)
ds_pts = ds_obs[cvar]
ds_pts = ds_pts.sel(Time_UTC=slice(sDate, eDate))

# Trim stations to domain of interest (allow some padding to included
# stations around boarder

ds_pts = ds_pts.where((ds_pts.Lat>lat_r[0]-bdy) & (ds_pts.Lat<lat_r[1]+bdy) &
                      (ds_pts.Lon>lon_r[0]-bdy) &
                  (ds_pts.Lon<lon_r[1]+bdy), drop=True)

# Get sum for checking data QC
ds_pts_sum = ds_pts.sum(dim='Time_UTC')

# preciping = ds_pts>0
# ds_pts = ds_pts.where(preciping,drop=True)
# ds_pts = ds_pts.isel(Time_UTC=0)
# ds_pts.data = np.random.randn(ds_pts.size)

# Drop missing stations
ds_pts = ds_pts.where((ds_pts_sum!=0) & (ds_pts_sum.notnull()) &
                      (ds_pts.Lon.notnull()) & (ds_pts.Lat.notnull())
                      & (ds_pts.Elevation.notnull()), drop=True)
# Drop bad stations w/o any precip (need to do in QC step)
# ds_pts = ds_pts.where(ds_pts_sum > ds_pts_sum.max()*0.2, drop=True)

# Plot check timeseries of cummulative precipitation
plt.figure()
plt.plot(ds_pts.Time_UTC, ds_pts.cumsum(dim='Time_UTC'))

# Get obs info
x = ds_pts.Lon.values
y = ds_pts.Lat.values
E = ds_pts.Elevation.values

# Get model(target) info
xi = ds_gem.gridlon_0
yi = ds_gem.gridlat_0
Ei = ds_gem.HGT_P0_L1_GST0

# Initialize dataArray
da_list = []

test_plots = False

# Loop through time
for t in ds_pts.Time_UTC: #.sel(Time_UTC=slice('2014-11-28T00:00:00', '2014-11-29T01:00:00')):
    # Get current time
    cval = ds_pts.sel(Time_UTC=t)
    print(t.values)

    # Set up IDW
    w = idw.IDW(x, y, xi, yi, mz=E, GridZ=Ei, power=2)

    # Check we have some observations
    if cval.notnull().sum()==0:
        print(t)
        raise ValueError('No stations with data on this time step found')

    # De-trend (wrt Elevation)
    cval_grid = w.detrendedIDW(cval.values, 0, zeros=None)
    cval_grid = cval_grid.where(cval_grid >= 0).fillna(0)
    cval_grid = cval_grid.where(Ei.notnull()) # Replace original missing cells

    # Add time stamp
    cval_grid['Time_UTC'] = t

    # Store interpolated grid
    da_list.append(cval_grid)

    # # Plot checks
    if test_plots and cval.max()*1000>5:
        # Check for trend with elevation
        plt.figure()
        plt.plot(cval.values*1000, cval.Elevation.values, 'ko')
        plt.ylabel('Elevatoin (m)')
        plt.xlabel('Precipitation\n(mm/hour)')
        plt.tight_layout()

        p_colors = matplotlib.colors.ListedColormap(sns.color_palette("Reds", 12))
        p_elev = matplotlib.colors.ListedColormap(sns.color_palette("Greys", 12))

        # Plot point obs on elevation map
        fig, ax = plt.subplots()
        Zm = ma.masked_invalid(Ei.values)
        e=plt.pcolormesh(Ei.gridlon_0, Ei.gridlat_0,
                       Zm, cmap=p_elev,
                       vmin=np.nanmin(Ei.values),
                       vmax=np.nanmax(Ei.values))
        cbar = plt.colorbar(e)
        cbar.ax.set_ylabel('Elevation (m)')
        # plot data points.
        # plt.scatter(x, y, marker='o', c='k', s=100, cmap=p_colors)
        pts1 = plt.scatter(x, y, marker='o', c=cval.values*1000, s=90, cmap=p_colors,
                    edgecolors='k', linewidths=2)
        cbar2 = plt.colorbar(pts1)
        cbar2.ax.set_ylabel('Precipitation (mm/hour)')

        # Plot interpolated obs
        plt.figure()
        Zm = ma.masked_invalid(cval_grid.values * 1000)
        plt.pcolormesh(cval_grid.gridlon_0, cval_grid.gridlat_0,
                       Zm, cmap=p_colors,
                       vmin=np.nanmin(cval_grid.values * 1000),
                       vmax=np.nanmax(cval_grid.values * 1000))

        cbar = plt.colorbar()
        cbar.ax.set_ylabel('Precipitation (mm/hour)')
        # plt.scatter(x, y, marker='o', c='k', s=100, cmap=p_colors)
        plt.scatter(x, y, marker='o', c=cval.values * 1000, s=90, cmap=p_colors,
                    edgecolors='k', linewidths=2)


        plt.show()

# Concat over time
da_grid = xr.concat(da_list, dim='Time_UTC')

# Set correct variable name
da_grid.name = cvar

# Save to netcdf file
print('NOT Saving here, need to uncomment')
# da_grid.to_netcdf(nc_file_out)




#
# # grid the data.
# zi = griddata((x, y), z, (xi, yi), method='linear')
# print(np.nanmax(zi), np.nanmin(zi))
#
# Plot contour the gridded data and points
# p_colors = matplotlib.colors.ListedColormap(sns.color_palette("Reds", 12))
# plt.figure()
# plt.pcolormesh(xi, yi, zi, cmap=p_colors, vmin=np.nanmin(z), vmax=np.nanmax(z))
# plt.colorbar()
# # plot data points.
# plt.scatter(x,y,marker='o',c='k',s=10, cmap=p_colors)
# plt.scatter(x,y,marker='o',c=z,s=6, cmap=p_colors)
#
#
#





