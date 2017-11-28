import matplotlib as mpl
# mpl.use('Agg')
import numpy as np
import matplotlib.pyplot as plt
import xarray as xr
import sys
import imp
import os
import cartopy.crs as ccrs
import cartopy.io.shapereader as shpreader
import seaborn as sns
plt.rcParams.update({'figure.max_open_warning': 0})

crun = 'GDPS_Current'
# crun = 'HRDPS_Historical'

if crun=='HRDPS_Historical':
    gem_file_out = r'/media/data3/nicway/SnowCast/GEM_eval/hrdps.nc'
    obs_file_out = r'/media/data3/nicway/SnowCast/GEM_eval/hrdps_obs.nc'
elif crun=='GDPS_Current':
    gem_file_out = r'/media/data3/nicway/SnowCast/GEM_eval/gdps.nc'
    obs_file_out = r'/media/data3/nicway/SnowCast/GEM_eval/gdps_obs.nc'
else:
    sys.exit('Run name not found.')    

plot_key = {'ilwr_out':'Outgoing Longwave','T_s_0':'Surface temperature','t':'Air Temperature','rh':'Relative Humidity',
            'p':'Precipitation','ilwr':'Incoming Longwave','iswr':'Shortwave Radiation',
            'U_2m_above_srf':'Wind Speed','vw_dir':'Wind Direction','swe':'Snow Water Equivalent','snowdepthavg':'Snowdepth'}

ylabel_unit = {'ilwr_out':'W m-2','G':'W m-2','T_s_0':'C','t':'C','rh':'%','p':'m','ilwr':'W m-2','iswr':'W m-2',
            'U_2m_above_srf':'m/s','vw_dir':'degrees true north','swe':'m','snowdepthavg':'m'}


gem_mrg = xr.open_dataset(gem_file_out)
gem_mrg = gem_mrg.where(gem_mrg!=-9999)
obs_mrg = xr.open_dataset(obs_file_out)

# GDPS and HRDPS precip in mm (convert here to m)
gem_mrg['p'] = gem_mrg.p / 1000


trim_extent = True
lat_r = [50.66,51.7933333333333]
lon_r = [-116.645,-114.769166666667]
if trim_extent:
    gem_mrg = gem_mrg.where((gem_mrg.Lat >= lat_r[0]) & (gem_mrg.Lat <= lat_r[1]) & (gem_mrg.Lon >= lon_r[0]) & (gem_mrg.Lon <= lon_r[1]), drop=True)
    obs_mrg = obs_mrg.where((obs_mrg.Lat >= lat_r[0]) & (obs_mrg.Lat <= lat_r[1]) & (obs_mrg.Lon >= lon_r[0]) & (obs_mrg.Lon <= lon_r[1]), drop=True)

# For each variable
# Calculate error metrics

ds_bias = (gem_mrg - obs_mrg).mean(dim='initDate')
ds_bias['p'] = (gem_mrg.p - obs_mrg.p).sum(dim='initDate')
print(ds_bias)

se = (gem_mrg - obs_mrg)**2.0
ds_rmse = xr.ufuncs.sqrt(se.mean(dim='initDate'))
print(ds_rmse)

# Plot

#plt.figure()
#plt.plot(gem_mrg.forecastHour, gem_mrg.iswr.isel(initDate=0).sel(station='FRG'))
#plt.plot(obs_mrg.forecastHour, obs_mrg.iswr.isel(initDate=0).sel(station='FRG'))
#plt.show()

# Bias
Vars_to_plot = ['t','rh','U_2m_above_srf','p','ilwr','iswr']

# Create a new figure and subplots for each variable
(f, ax1) = plt.subplots(2, 3, sharey=False)
f.set_size_inches(16, 8)
ax1 = ax1.flatten()
for i,cvar in enumerate(Vars_to_plot):
    ax1[i].plot(ds_bias.forecastHour, ds_bias[cvar].T ,'-k',)
    ax1[i].plot(ds_bias.forecastHour, ds_bias[cvar].mean(dim='station'), linewidth=3, color='r')
    ax1[i].set_title(plot_key[cvar])
    ax1[i].set_ylabel(ylabel_unit[cvar])

(f2, ax1) = plt.subplots(2, 3, sharey=False)
f2.set_size_inches(16, 8)
ax1 = ax1.flatten()
for i,cvar in enumerate(Vars_to_plot):
    ax1[i].plot(ds_rmse.forecastHour, ds_rmse[cvar].T ,'-k',)
    ax1[i].plot(ds_rmse.forecastHour, ds_rmse[cvar].mean(dim='station'), linewidth=3, color='r')
    ax1[i].set_title(plot_key[cvar])
    ax1[i].set_ylabel(ylabel_unit[cvar])

(f3, ax1) = plt.subplots(2, 3, sharey=False)
f3.set_size_inches(16, 8)
ax1 = ax1.flatten()
for i, cvar in enumerate(Vars_to_plot):
    ax1[i].plot(gem_mrg.forecastHour, gem_mrg[cvar].mean(dim='station').T, '-r', )
    ax1[i].plot(obs_mrg.forecastHour, obs_mrg[cvar].mean(dim='station').T, '-b')
    ax1[i].set_title(plot_key[cvar])
    ax1[i].set_ylabel(ylabel_unit[cvar])

plt.show()















