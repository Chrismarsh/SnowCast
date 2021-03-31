# Evaluate CHM at Snow coarse sites

import imp
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import os
# Plot settings
import seaborn as sns
import sys
import xarray as xr
# matplotlib.use('Agg')
from matplotlib import markers

sns.set_style('whitegrid')
# sns.set_style('ticks')
sns.set_context("talk", font_scale=1.5, rc={"lines.linewidth": 2.5})

# General plotting settings
fig_res = 90 # dpi

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

main_dir = os.path.join(git_dir, 'CHM_Configs', chm_run_dir)
fig_dir = os.path.join(main_dir, 'figures', 'Point_Evals')

# Make fig dir
if not os.path.isdir(os.path.join(main_dir, 'figures')):
    os.mkdir(os.path.join(main_dir, 'figures'))
if not os.path.isdir(fig_dir):
    os.mkdir(fig_dir)

def save_figure(f,file_out,fig_res):
    f.savefig(file_out,bbox_inches='tight',dpi=fig_res)

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
#file_in = os.path.join(data_dir, 'QC', 'Hourly_QC.nc') # CRHO and other data
snow_survey_in  = os.path.join(data_dir, 'CRHO_HIST', 'netcdf', 'CRHO_Snow_Survey_Individual.nc')
EC_snow_course_in = os.path.join(data_dir, 'EC_Snow_Courses', 'netcdf', 'EC_Snow_Courses.nc')

# Snow surveys
SS_data = xr.open_dataset(snow_survey_in,engine='netcdf4')
EC_data = xr.open_dataset(EC_snow_course_in).load()

# For current exp/folder, get netcdf file
c_mod_file = os.path.join(main_dir,'points','CHM_pts.nc')
Mod_data = xr.open_dataset(c_mod_file, engine='netcdf4')
dt_eval_hr = {'H':1, '3H':3, 'MS':999999, 'W':999999} # This converts resample() strs to int hours. Use 999 if N/A.

EC_data.rename({'staID':'station', 'Time_UTC':'time', 'SnowDepth_point':'snowdepthavg', 'SWE_point':'swe'}, inplace=True);

TODO: merge in CRHO Survey data!! (need to take average and rename)

# Function that makes two data sets common:
# Variables
# Time Step
# Stations
def make_common_snow_coarse(ds_obs, ds_mod, dt_eval):
    # dt_eval = 'H' # MS (month start), H (hour), W (week)
    
    # Common variables
    obs_vars = ds_obs.data_vars
    mod_vars = ds_mod.data_vars
    # Find common variables
    com_vars = np.sort(list(set(obs_vars).intersection(mod_vars)))
    # Extract only common vars
    ds_obs=ds_obs[com_vars]
    ds_mod=ds_mod[com_vars]
    print("Common variables are:",com_vars)
    print("")

    # Common stations
    obs_sta = ds_obs['station'].values
    mod_sta = ds_mod['station'].values #[x.decode('UTF-8') for x in ds_mod['station'].values]
    # Find common variables
    com_sta = np.sort(list(set(obs_sta).intersection(mod_sta)))
    print("Common stations are:",com_sta)
    print("")
    if len(com_sta)==0:
        print(obs_sta)
        print(mod_sta)
        raise ValueError('No common stations found')

    # Extract only common stations
    ds_obs=ds_obs.sel(station=com_sta)
    ds_mod=ds_mod.sel(station=com_sta)

    # Pre-trim time to common time (speeds up time step aggregation)
    T_start = np.max([ds_mod.time.values[0], ds_obs.time.values[0]])
    T_end = np.min([ds_mod.time.values[-1], ds_obs.time.values[-1]])
    print(T_start, T_end)
    ds_obs = ds_obs.where((ds_obs.time>=T_start) & (ds_obs.time<=T_end), drop=True)
    ds_mod = ds_mod.where((ds_mod.time>=T_start) & (ds_mod.time<=T_end), drop=True)

    # Common time period
    #agg time
    com_time = np.intersect1d(ds_mod.time, ds_obs.time)
    if len(com_time)==0:
        raise ValueError("no common time found")

    print("Common time is:",com_time.size," from ",com_time[0], " to ", com_time[-1])
    print("")
    obs_dt_val = ds_obs.sel(time=com_time).load()
    mod_dt_val = ds_mod.sel(time=com_time).load()

    # Clean up
    #ds_mod = None
    #ds_obs = None
    
    return (obs_dt_val, mod_dt_val)

# Get common obs and model
(obs_dt_val, mod_dt_val) = make_common_snow_coarse(EC_data, Mod_data, 'point')

# Memory Clean up
OBS_data = None
Mod_data = None

sta_list = np.sort(mod_dt_val.station)

# Function to plot mod/obs at snow coarse points
def plot_var_at_snowCoarse(cvar, ds_MOD, ds_OBS):

    # Create a new figure and subplots for each variable
    (f, ax1) = plt.subplots(1, 1, sharey=False)
    f.set_size_inches(16, 6)
    #### Loop through each station
    # Find stations with obs/mod data
    sta_w_data = ds_MOD.station.where((ds_MOD[cvar].notnull().sum(dim='time')>0) & (ds_OBS[cvar].notnull().sum(dim='time')>0), drop=True).values
    # print(sta_w_data)

    # c_sta_clrs = ['b','g','r','c','m','y','k', 'b','g','r','c','m','y','k', 'b','g','r','c','k', 'b','g','r',
    #         'c','m','y','k', 'b','g','r','c','k', 'b','g','r','c','m','y','k', 'b','g','r','c','k']
    # c_sta_cmap = dict(zip(sta_w_data, sta_clrs))
    #
    # #c_sta_mrks = ['d', '+', '1', 'v', 'o', '*','2','3','4','8','s']
    # #c_sta_mrks = markers.MarkerStyle.markers.keys()
    # c_sta_marks = ['1', '2', '3', '4', u'D', '8', u's', u'|', 11, u'P', 9, u'x', u'X', 5, u'_', u'^', u' ', u'd', u'h', u'+', u'*', u'o', u'.', u'p', u'H', u'v', u'', u'<', u'>']
    # print(c_sta_marks)
    # c_sta_Mmap = dict(zip(sta_w_data, c_sta_marks))

    h_mod = []
    h_obs = []
    #### Loop through each station
    for csta in sta_w_data:
        # Get mod and obs arrays
        c_mod = ds_MOD[cvar].sel(station=csta)
        c_obs = ds_OBS[cvar].sel(station=csta)
        # print(csta)
        # print(c_sta_Mmap[csta])
        # Plot model/obs to get quick check
        hm = ax1.scatter(c_mod.time.values, c_mod.values, facecolors='None', edgecolors='r',
                         s=100, marker='o', linewidths=1.5,
                         label=str(ds_OBS.station_name.sel(station=csta).values))
        # ax1.plot(c_mod.time.values, c_mod.values, 'r')

        ho = ax1.scatter(c_obs.time.values, c_obs.values, facecolors='None', edgecolors='b',
                         s=100, marker='d',linewidths=2,
                         label=str(ds_OBS.station_name.sel(station=csta).values))
        # ax1.plot(c_obs.time.values, c_obs.values, 'b')

        # hm, = c_mod.plot(color=c_sta_cmap[csta],ax=ax1,marker='o', linestyle='None',
        #           label=str(ds_OBS.station_name.sel(station=csta).values))
        # ho, = c_obs.plot(color=c_sta_cmap[csta], marker='s', linestyle='None',
        #           ax=ax1,label=str(ds_OBS.station_name.sel(station=csta).values))

        # Store legend handels
        h_mod.append(hm)
        h_obs.append(ho)

    ax1.set_title(plot_key[cvar])
    ax1.set_ylabel(plot_key[cvar]+' ('+ylabel_unit[cvar]+')')
    # ax1.set_ylim([0, 1.5])
    f.tight_layout()
    # Add Legends
    first_legend = plt.legend(handles=h_obs, loc='upper left')
    # ax = ax1.add_artist(first_legend)
    plt.legend([h_obs[0],h_mod[1]], ['Observed', 'Modeled'], loc='upper left')
    leg = ax1.get_legend()
    # leg.legendHandles[0].set_color('blue')
    # leg.legendHandles[1].set_color('red')

    # Save Figure
    file_out = os.path.join(fig_dir, 'Survey_' + cvar + '.png')
    save_figure(f,file_out,fig_res)

    # How well can we Simulate point SWE?
    # Create a new figure and subplots for each variable
    (f2, ax1) = plt.subplots(1, 1, sharey=False)
    f2.set_size_inches(16, 6)
    #### Loop through each station
    v_c = 0
    # Find stations with obs/mod data
    sta_w_data = ds_MOD.station.where(
        (ds_MOD[cvar].notnull().sum(dim='time') > 0) & (ds_OBS[cvar].notnull().sum(dim='time') > 0),
        drop=True).values
    # print(sta_w_data)

    # c_sta_clrs = ['b','g','r','c','m','y','k', 'b','g','r','c','m','y','k', 'b','g','r','c','k', 'b','g','r',
    #         'c','m','y','k', 'b','g','r','c','k', 'b','g','r','c','m','y','k', 'b','g','r','c','k']
    # c_sta_cmap = dict(zip(sta_w_data, sta_clrs))
    #
    # #c_sta_mrks = ['d', '+', '1', 'v', 'o', '*','2','3','4','8','s']
    # #c_sta_mrks = markers.MarkerStyle.markers.keys()
    # c_sta_marks = ['1', '2', '3', '4', u'D', '8', u's', u'|', 11, u'P', 9, u'x', u'X', 5, u'_', u'^', u' ', u'd', u'h', u'+', u'*', u'o', u'.', u'p', u'H', u'v', u'', u'<', u'>']
    # print(c_sta_marks)
    # c_sta_Mmap = dict(zip(sta_w_data, c_sta_marks))

    h_mod = []
    h_obs = []
    #### Loop through each station
    for csta in sta_w_data:
        # Get mod and obs arrays
        c_mod = ds_MOD[cvar].sel(station=csta)
        c_obs = ds_OBS[cvar].sel(station=csta)
        # print(csta)
        # print(c_sta_Mmap[csta])
        # Plot model/obs to get quick check
        hm = ax1.scatter(c_mod.time.values, c_mod.values - c_obs.values, facecolors='None', edgecolors='k',
                         s=100, marker='o', linewidths=1.5,
                         label=str(ds_OBS.station_name.sel(station=csta).values));

        # Store legend handels
        # print(hm)
        h_mod.append(hm)
        # h_obs.append(ho)

    ax1.set_title(plot_key[cvar])
    ax1.set_ylabel(plot_key[cvar] + ' bias (' + ylabel_unit[cvar] + ')')
    # ax1.set_ylim([-0.4, 0.81])
    f2.tight_layout()
    # Add Legend
    plt.legend([h_mod[0]], ['Bias (Model - Observed)'], loc='upper left')

    # Save Figure
    file_out = os.path.join(fig_dir, 'Survey_' + cvar + '_diff.png')
    save_figure(f2, file_out, fig_res)

# Call plot and save functions
plot_var_at_snowCoarse('swe', mod_dt_val, obs_dt_val)
plot_var_at_snowCoarse('snowdepthavg', mod_dt_val, obs_dt_val)

print("Finished plotting snow coarse comparison")
