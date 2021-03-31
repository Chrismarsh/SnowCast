# Evaluate GEM-CHM Met and Snow to stations

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
sns.set_style('whitegrid')
sns.set_context("talk", font_scale=1.5, rc={"lines.linewidth": 2.5})
fig_res = 90 # dpi

# Some plotting Options
percent_nan_allowed = 80 # % to allow missing from aggregation period (varies)
exclude_forest = 0  # 0 - non-forest only
                    # 1 - forest only
                    # 2 - all stations
# Forested stations
forest_staID = ['HMW', 'LLF', 'UPC', 'UPF']

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) != 3:
    raise ValueError('Requires two arguments [configuration file] [chm_run_dir]')

# Get name of configuration file/module
configfile = sys.argv[1]
chm_run_dir = str(sys.argv[2])

if chm_run_dir=='forecast_CRHO_spinup':
    c_run_dt_in = 'H'
elif chm_run_dir=='HRDPS_Current_BS':
    c_run_dt_in = 'H'
elif chm_run_dir=='HRDPS_Historical':
    c_run_dt_in = 'D'
elif chm_run_dir=='HRDPS_Historical_Post_Processed':
    c_run_dt_in = 'W'
elif chm_run_dir=='GDPS_Current':
    c_run_dt_in = '3H'
else:
    sys.exit('Model run name not found')

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
data_dir = X.data_dir
git_dir   = X.git_dir

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

ylabel_unit = {'ilwr_out':'W m-2','G':'W m-2','T_s_0':'C','t':'C','rh':'%','p':'m','ilwr':'W m-2','iswr':'W m-2',
            'U_2m_above_srf':'m/s','vw_dir':'degrees true north','swe':'m','snowdepthavg':'m'}


# Data files in
file_in = os.path.join(data_dir, 'QC', 'Hourly_QC.nc') # CRHO and other data
snow_survey_in  = os.path.join(data_dir, 'CRHO_HIST', 'netcdf', 'CRHO_Snow_Survey_Individual.nc')
EC_snow_course_in = os.path.join(data_dir, 'EC_Snow_Courses', 'netcdf', 'EC_Snow_Courses.nc')

# Load all obs
OBS_data = xr.open_dataset(file_in, engine='netcdf4') #.load()
# Rename obs variable names to model variable names
OBS_data.rename(vars_all, inplace=True);

# # Filling in missing SW values at night (these were negative values that in QC SHOULD have been set to zero)
# OBS_data['iswr'] = OBS_data['iswr'].fillna(0)
# print('iswr fill is hack, need to fix upstream')

# For current exp/folder, get netcdf file
c_mod_file = os.path.join(main_dir,'points','CHM_pts.nc')
Mod_data = xr.open_dataset(c_mod_file,engine='netcdf4')
dt_eval_hr = {'H':1, '3H':3, 'D':24, 'MS':999999, 'W':999999} # This converts resample() strs to int hours. Use 999 if N/A.

# Get common obs and model
print("Allowing ",percent_nan_allowed," percent missing in period averages.")
(obs_dt_val, mod_dt_val) = chmF.make_common(OBS_data, Mod_data,
        c_run_dt_in, dt_eval_hr, remove_missing=True,
        percent_nan_allowed=percent_nan_allowed,
        exclude_forest=exclude_forest, forest_staID=forest_staID)

# Memory Clean up
OBS_data = None
Mod_data = None

sta_list = np.sort(mod_dt_val.station)

## Time series plots
#cmap = colors.ListedColormap(['white', 'red'])
sta_clrs = ['b','g','r','c','m','y','k', 'b','g','r','c','m','y','k', 'b','g','r','c','k', 'b','g','r',
            'c','m','y','k', 'b','g','r','c','k', 'b','g','r','c','m','y','k', 'b','g','r','c','k']
sta_cmap = dict(zip(mod_dt_val.station.values, sta_clrs))

obs_linewidth = 2.5
mod_linewidth = 2


# How well can we Simulate point SWE?
Vars_to_plot = ['swe']
# Create a new figure and subplots for each variable
(f, ax1) = plt.subplots(1, 1, sharey=False)
f.set_size_inches(16, 6)
#### Loop through each station
v_c = 0
for cvar in Vars_to_plot:
    # Find stations with obs/mod data
    sta_w_data = mod_dt_val.station.where((mod_dt_val[cvar].notnull().sum(dim='time')>0) & (obs_dt_val[cvar].notnull().sum(dim='time')>0), drop=True).values
    print(sta_w_data)

    c_sta_clrs = ['b','g','r','c','m','y','k', 'b','g','r','c','m','y','k', 'b','g','r','c','k', 'b','g','r',
            'c','m','y','k', 'b','g','r','c','k', 'b','g','r','c','m','y','k', 'b','g','r','c','k']
    c_sta_cmap = dict(zip(sta_w_data, sta_clrs))

    h_mod = []
    h_obs = []    
    #### Loop through each station
    for csta in sta_w_data:
        # Get mod and obs arrays
        c_mod = mod_dt_val[cvar].sel(station=csta)
        c_obs = obs_dt_val[cvar].sel(station=csta)
        print(csta)
        
        # Plot model/obs to get quick check
        if(cvar!='p'):
            hm, = c_mod.plot.line(color=c_sta_cmap[csta],ax=ax1,linestyle='--',
                  linewidth=mod_linewidth,label=str(obs_dt_val.station_name.sel(station=csta).values))
            ho, = c_obs.plot.line(color=c_sta_cmap[csta],
                  linewidth=obs_linewidth,ax=ax1,label=str(obs_dt_val.station_name.sel(station=csta).values))
        else:
            # Check there is any precip measured (bug from above where missing all nanas, are averaged to zeros...)
            hm, = np.cumsum(c_mod).plot.line(color=c_sta_cmap[csta],ax=ax1,linestyle='--',linewidth=mod_linewidth)
            ho, = np.cumsum(c_obs).plot.line(color=c_sta_cmap[csta],linewidth=obs_linewidth,ax=ax1)
        # Store legend handels
        print(hm)    
        h_mod.append(hm)
        h_obs.append(ho)

    ax1.set_title(plot_key[cvar])
    ax1.set_ylabel('SWE ('+ylabel_unit[cvar]+')')
            
    # incremetn axes                        
    v_c = v_c + 1
f.tight_layout()
# Add Legends
first_legend = plt.legend(handles=h_obs, loc='upper left')
ax = ax1.add_artist(first_legend)
if (len(h_obs)!=0)  & (len(h_mod)!=0):
    plt.legend([h_obs[0],h_mod[0]], ['Observed', 'Modeled'], loc='upper center')
    leg = ax1.get_legend()
    leg.legendHandles[0].set_color('black')
    leg.legendHandles[1].set_color('black')

# Save Figure
file_out = os.path.join(fig_dir, 'Point_' + Vars_to_plot[0] + '.png')
chmF.save_figure(f,file_out,fig_res)


#
# for csta in mod_dt_val.station:
#     plt.figure()
#     plt.title(str(csta.values))
#     plt.plot(mod_dt_val.time, mod_dt_val['swe'].sel(station=csta))

Vars_to_plot = ['snowdepthavg']

# Create a new figure and subplots for each variable
(f, ax1) = plt.subplots(1, 1, sharey=False)
f.set_size_inches(16, 6)
# ax1 = ax1.flatten()

#### Loop through each station
v_c = 0
first_sta = True
for cvar in Vars_to_plot:
    #     h_m = [] # init handles for plots
    #     h_o = []
    #### Loop through each station
    for csta in sta_list:
        # Get mod and obs arrays
        c_mod = mod_dt_val[cvar].sel(station=csta)
        c_obs = obs_dt_val[cvar].sel(station=csta)
        # Find non-nan values
        I_not_nans = ~c_mod.isnull() & ~c_obs.isnull()
        # If any non-nan, take metrics
        if np.any(I_not_nans)  and sum(c_obs)!=0: # last check is to remove SW stations with all zeros 
            # print ('CHECK THIS is not shifting the time...')
            print(csta, " ", str(obs_dt_val.station_name.sel(station=csta).values))
            
            # labels
            if first_sta:
                obs_label = 'Observed'
                mod_label = 'Model'
                first_sta = False
            else:
                obs_label = '_nolegend_' 
                mod_label = '_nolegend_'
            # Plot model/obs to get quick check
            if(cvar!='p'):
                c_mod.plot.line(marker='.',color='r',ax=ax1,linestyle='--',linewidth=mod_linewidth, label=mod_label)
                c_obs.plot.line(color='b',linewidth=obs_linewidth,ax=ax1, label=obs_label)
            else:
                # Check there is any precip measured (bug from above where missing all nanas, are avveraged to zeros...)
                if np.all(sum(c_mod)>0 and sum(c_obs)>0):
                    np.cumsum(c_mod).plot.line(marker='.',color='r',ax=ax1,linestyle='--',linewidth=mod_linewidth)
                    np.cumsum(c_obs).plot.line(color='b',linewidth=obs_linewidth,ax=ax1)
            ax1.set_title(plot_key[cvar])
            ax1.set_ylabel('Snow Depth ('+ylabel_unit[cvar]+')')
            
            
    # incremetn axes                        
    v_c = v_c + 1
f.tight_layout()
plt.legend(loc='upper left')
file_out = os.path.join(fig_dir, 'Point_' + Vars_to_plot[0] + '.png')
chmF.save_figure(f,file_out,fig_res)



Vars_to_plot = ['t']
# Create a new figure and subplots for each variable
(f, ax1) = plt.subplots(1, 1, sharey=False)
f.set_size_inches(16, 6)
# ax1 = ax1.flatten()

#### Loop through each station
v_c = 0
first_sta = True
for cvar in Vars_to_plot:
    #     h_m = [] # init handles for plots
    #     h_o = []
    #### Loop through each station
    for csta in sta_list:
        # Get mod and obs arrays
        c_mod = mod_dt_val[cvar].sel(station=csta)
        c_obs = obs_dt_val[cvar].sel(station=csta)
        # Find non-nan values
        I_not_nans = ~c_mod.isnull() & ~c_obs.isnull()
        # If any non-nan, take metrics
        if np.any(I_not_nans)  and sum(c_obs)!=0: # last check is to remove SW stations with all zeros 
            # print ('CHECK THIS is not shifting the time...')
            print(csta)

             # labels
            if first_sta:
                obs_label = 'Observed'
                mod_label = 'Model'
                first_sta = False
            else:
                obs_label = '_nolegend_'
                mod_label = '_nolegend_'
            
            # Plot model/obs to get quick check
            if(cvar!='p'):
                c_mod.plot.line(marker='.',color='r',ax=ax1,linestyle='--',linewidth=mod_linewidth, label=mod_label)
                c_obs.plot.line(color='b',linewidth=obs_linewidth,ax=ax1, label=obs_label)
            else:
                # Check there is any precip measured (bug from above where missing all nanas, are avveraged to zeros...)
                if np.all(sum(c_mod)>0 and sum(c_obs)>0):
                    np.cumsum(c_mod).plot.line(marker='.',color='r',ax=ax1,linestyle='--',linewidth=mod_linewidth)
                    np.cumsum(c_obs).plot.line(color='b',linewidth=obs_linewidth,ax=ax1)
            ax1.set_title(plot_key[cvar])
            ax1.set_ylabel('Air Temp. ('+ylabel_unit[cvar]+')')
            
            
    # incremetn axes                        
    v_c = v_c + 1
f.tight_layout()
plt.legend(loc='upper right')
file_out = os.path.join(fig_dir, 'Point_' + Vars_to_plot[0] + '.png')
chmF.save_figure(f,file_out,fig_res)

# plt.show()
