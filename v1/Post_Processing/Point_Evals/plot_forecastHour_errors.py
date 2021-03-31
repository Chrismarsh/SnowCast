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
import CHM_functions as chmF


plt.rcParams.update({'figure.max_open_warning': 0})
# General plotting settings
sns.set_style('whitegrid')
sns.set_context("talk", font_scale=1.5, rc={"lines.linewidth": 2.5})
fig_res = 90 # dpi

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) != 3:
    sys.exit('Requires two arguments [configuration file] [chm_run_dir]')

# Get name of configuration file/module
configfile = sys.argv[1]
chm_run_dir = str(sys.argv[2])

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
data_dir = X.data_dir
git_dir   = X.git_dir

main_dir  = os.path.join(git_dir, 'CHM_Configs', chm_run_dir)
fig_dir   = os.path.join(main_dir , 'figures', 'Forecast_Evals')

# Make fig dir
if not os.path.isdir(os.path.join(main_dir, 'figures')):
    os.mkdir(os.path.join(main_dir, 'figures'))
if not os.path.isdir(fig_dir):
    os.mkdir(fig_dir)

# Hardcoded paths
if chm_run_dir=='forecast_CRHO_spinup':
    gem_file_out = r'/media/data3/nicway/SnowCast/GEM_eval/hrdps.nc'
    obs_file_out = r'/media/data3/nicway/SnowCast/GEM_eval/hrdps_obs.nc'
    h_dt = 1 # Hours per gem tim step
elif chm_run_dir=='GDPS_Current':
    gem_file_out = r'/media/data3/nicway/SnowCast/GEM_eval/gdps.nc'
    obs_file_out = r'/media/data3/nicway/SnowCast/GEM_eval/gdps_obs.nc'
    h_dt = 3 # Hours per gem tim step
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
# print(ds_bias)

se = (gem_mrg - obs_mrg)**2.0
ds_rmse = xr.ufuncs.sqrt(se.mean(dim='initDate'))
# print(ds_rmse)

# Plot

#plt.figure()
#plt.plot(gem_mrg.forecastHour, gem_mrg.iswr.isel(initDate=0).sel(station='FRG'))
#plt.plot(obs_mrg.forecastHour, obs_mrg.iswr.isel(initDate=0).sel(station='FRG'))
#plt.show()

# Bias
Vars_to_plot = ['t','rh','U_2m_above_srf','p','ilwr','iswr']

# Create a new figure and subplots for each variable
(f1, ax1) = plt.subplots(2, 3, sharey=False)
f1.set_size_inches(16, 8)
ax1 = ax1.flatten()
for i,cvar in enumerate(Vars_to_plot):
    ax1[i].plot(ds_bias.forecastHour*h_dt, ds_bias[cvar].T ,'-k',)
    ax1[i].plot(ds_bias.forecastHour*h_dt, ds_bias[cvar].mean(dim='station'), linewidth=3, color='r')
    ax1[i].set_title(plot_key[cvar])
    ax1[i].set_ylabel(ylabel_unit[cvar])
    if i==4:
        ax1[i].set_xlabel('Forecast hour')
f1.tight_layout()
# Save Figure
file_out = os.path.join(fig_dir, 'Bias.png')
chmF.save_figure(f1,file_out,fig_res)

(f2, ax1) = plt.subplots(2, 3, sharey=False)
f2.set_size_inches(16, 8)
ax1 = ax1.flatten()
for i,cvar in enumerate(Vars_to_plot):
    ax1[i].plot(ds_rmse.forecastHour*h_dt, ds_rmse[cvar].T ,'-k',)
    ax1[i].plot(ds_rmse.forecastHour*h_dt, ds_rmse[cvar].mean(dim='station'), linewidth=3, color='r')
    ax1[i].set_title(plot_key[cvar])
    ax1[i].set_ylabel(ylabel_unit[cvar])
    if i==4:
        ax1[i].set_xlabel('Forecast hour')
f2.tight_layout()
# Save Figure
file_out = os.path.join(fig_dir, 'RMSE.png')
chmF.save_figure(f2, file_out, fig_res)

(f3, ax1) = plt.subplots(2, 3, sharey=False)
f3.set_size_inches(16, 8)
ax1 = ax1.flatten()
for i, cvar in enumerate(Vars_to_plot):
    ax1[i].plot(gem_mrg.forecastHour*h_dt, gem_mrg[cvar].mean(dim='station').T, '-r', )
    ax1[i].plot(obs_mrg.forecastHour*h_dt, obs_mrg[cvar].mean(dim='station').T, '-b')
    ax1[i].set_title(plot_key[cvar])
    ax1[i].set_ylabel(ylabel_unit[cvar])
    if i==4:
        ax1[i].set_xlabel('Forecast hour')
f3.tight_layout()
# Save Figure
file_out = os.path.join(fig_dir, 'Met.png')
chmF.save_figure(f3,file_out,fig_res)

# plt.show()















