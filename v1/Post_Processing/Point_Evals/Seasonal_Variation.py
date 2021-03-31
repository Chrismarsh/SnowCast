# Evaluate GEM-CHM seasonal MET at stations

# Standard modules
import matplotlib
matplotlib.use('Agg')
import numpy as np
import matplotlib.pyplot as plt
import xarray as xr
import sys
import imp
import os
import seaborn as sns
plt.rcParams.update({'figure.max_open_warning': 0})
# SnowCast modules
import CHM_functions as chmF

# General plotting settings
sns.set_style('ticks')
sns.set_context("talk", font_scale=1.5, rc={"lines.linewidth": 2.5})
fig_res = 90 # dpi

# Some plotting Options
percent_nan_allowed = 50 # % to allow missing from aggregation period (varies)
exclude_forest = 0  # 0 - non-forest only
                    # 1 - forest only
                    # 2 - all stations
# Forested stations
forest_staID = ['HMW', 'LLF', 'UPC', 'UPF']
c_run_dt_in = 'MS' # MS (month start), H (hour), W (week)

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) != 3:
    raise ValueError('Requires two arguments [configuration file] [chm_run_dir]')

# Get name of configuration file/module
configfile = sys.argv[1]
chm_run_dir = str(sys.argv[2])

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
data_dir = X.data_dir
git_dir = X.git_dir

main_dir  = os.path.join(git_dir, 'CHM_Configs', chm_run_dir)
fig_dir   = os.path.join(main_dir , 'figures', 'Point_Evals')

# Make fig dir
if not os.path.isdir(os.path.join(main_dir, 'figures')):
    os.mkdir(os.path.join(main_dir, 'figures'))
if not os.path.isdir(fig_dir):
    os.mkdir(fig_dir)

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

ylabel_unit = {'ilwr_out':'W m-2','G':'W m-2','T_s_0':'(C)','t':'C','rh':'%','p':'m','ilwr':'W m-2','iswr':'W m-2',
            'U_2m_above_srf':'m/s','vw_dir':'degrees true north','swe':'m','snowdepthavg':'m'}

# Data files in
file_in = os.path.join(data_dir, 'QC', 'Hourly_QC.nc') # CRHO and other data

# Load all obs
OBS_data = xr.open_dataset(file_in, engine='netcdf4') #.load()
# Rename obs variable names to model variable names
OBS_data.rename(vars_all, inplace=True);

# Filling in missing SW values at night (these were negative values that in QC SHOULD have been set to zero)
# OBS_data['iswr'] = OBS_data['iswr'].fillna(0)
# print('iswr fill is hack, need to fix upstream')
# For current exp/folder, get netcdf file
c_mod_file = os.path.join(main_dir,'points','CHM_pts.nc')
print(c_mod_file)
Mod_data = xr.open_dataset(c_mod_file,engine='netcdf4')
dt_eval_hr = {'H':1, '3H':3, 'D':24, 'MS':999999, 'W':999999} # This converts resample() strs to int hours. Use 999 if N/A.



# Get common obs and model
(obs_dt_val, mod_dt_val) = chmF.make_common(OBS_data, Mod_data,
                           c_run_dt_in, dt_eval_hr,
                           remove_missing=True, percent_nan_allowed=20,
                           exclude_forest = exclude_forest,
                           forest_staID = forest_staID)

# Memory Clean up
OBS_data = None
Mod_data = None

sta_list = np.sort(mod_dt_val.station)

obs_linewidth = 2
mod_linewidth = 2


Vars_to_plot = ['t','rh','U_2m_above_srf','p','ilwr','iswr']

# Create a new figure and subplots for each variable
(f, ax1) = plt.subplots(2, 3, sharey=False)
f.set_size_inches(16, 8)
ax1 = ax1.flatten()

#### Loop through each station
v_c = 0
for cvar in Vars_to_plot:
    #     h_m = [] # init handles for plots
    #     h_o = []
    #### Loop through each station
    for csta in sta_list:
        # Get mod and obs arrays
        c_mod = mod_dt_val[cvar].sel(station=csta)
        c_obs = obs_dt_val[cvar].sel(station=csta)
        #Find non-nan values
        I_not_nans = ~c_mod.isnull() & ~c_obs.isnull()
        if np.any(I_not_nans):
            if(cvar!='p'):
                c_mod.plot.line(color='r',ax=ax1[v_c],linestyle='--',linewidth=mod_linewidth)
                c_obs.plot.line(color='b',linewidth=obs_linewidth,ax=ax1[v_c])
            else:
                if c_obs.sum()!=0:
                    c_mod.cumsum(dim='time').plot.line(color='r',ax=ax1[v_c],linestyle='--',linewidth=mod_linewidth)
                    c_obs.cumsum(dim='time').plot.line(color='b',linewidth=obs_linewidth,ax=ax1[v_c])
        ax1[v_c].set_title(plot_key[cvar])
        ax1[v_c].set_ylabel(ylabel_unit[cvar])
    # same x-axis limits
    ax1[v_c].set_xlim([mod_dt_val.time.isel(time=0).values,mod_dt_val.time.isel(time=-1).values])
    # increment axes
    v_c = v_c + 1
f.tight_layout()


# Save Figure
file_out = os.path.join(fig_dir, 'Seasonal_Met.png')
chmF.save_figure(f,file_out,fig_res)


Vars_to_plot = ['t','rh','U_2m_above_srf','p','ilwr','iswr']

# Create a new figure and subplots for each variable
(f2, ax1) = plt.subplots(2, 3, sharey=False)
f2.set_size_inches(16, 8)
ax1 = ax1.flatten()

#### Loop through each station
v_c = 0
for cvar in Vars_to_plot:
    #     h_m = [] # init handles for plots
    #     h_o = []
    #### Loop through each station
    for csta in sta_list:
        # Get mod and obs arrays
        c_mod = mod_dt_val[cvar].sel(station=csta)
        c_obs = obs_dt_val[cvar].sel(station=csta)
        #Find non-nan values
        I_not_nans = ~c_mod.isnull() & ~c_obs.isnull()
        if np.any(I_not_nans):
            if(cvar!='p'):
                (c_mod-c_obs).plot.line(color='k',ax=ax1[v_c],linestyle='-',linewidth=mod_linewidth)
                # c_obs.plot.line(color='b',linewidth=obs_linewidth,ax=ax1[v_c])
            else:
                if c_obs.sum()!=0:
                    (c_mod-c_obs).cumsum(dim='time').plot.line(color='k',ax=ax1[v_c],linestyle='-',linewidth=mod_linewidth)
                    # c_obs.plot.line(color='b',linewidth=obs_linewidth,ax=ax1[v_c])
        ax1[v_c].set_title(plot_key[cvar])
        ax1[v_c].set_ylabel(ylabel_unit[cvar])
    # same x-axis limits
    ax1[v_c].set_xlim([mod_dt_val.time.isel(time=0).values,mod_dt_val.time.isel(time=-1).values])
    # increment axes
    v_c = v_c + 1
f2.tight_layout()


# Save Figure
file_out = os.path.join(fig_dir, 'Seasonal_Met_Errors.png')
chmF.save_figure(f2,file_out,fig_res)



# plt.show()
