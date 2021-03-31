import matplotlib as mpl
import numpy as np
import os
import pandas as pd
import shutil
import sys

mpl.use('Agg')
import matplotlib.pyplot as plt
import glob
from pyproj import Proj, transform
import imp
import xarray as xr
import time
import vtk
from vtk.util import numpy_support as VN
import matplotlib.tri as tri
import vtu_functions as vfunc
import cartopy.crs as ccrs
import cartopy.io.shapereader as shpreader
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
import datetime
import seaborn as sns

# General plotting settings
sns.set_style('ticks')
sns.set_context("talk", font_scale=2, rc={"lines.linewidth": 2})
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
git_dir   = X.git_dir
data_dir = X.data_dir

# Dir to vtu files
main_dir  = os.path.join(git_dir, 'CHM_Configs', chm_run_dir)
vtu_dir   = os.path.join(main_dir, 'meshes')
fig_dir   = os.path.join(main_dir, 'figures')
prefix = 'SC'

last_N = 10 # last output CHM vtu files to plot

local_time_offset = -7 # Offset to local standard time (i.e. -7 for MST)

# Load in Obs

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


file_in = os.path.join(data_dir, 'QC', 'Hourly_QC.nc') # CRHO and other data
# Load all obs
OBS_data = xr.open_dataset(file_in, engine='netcdf4') #.load()
# Rename obs variable names to model variable names
OBS_data.rename(vars_all, inplace=True);

p_file = os.path.join(data_dir, 'Static_data', 'CAN_adm1.shp')
# Provences
p_sh = list(shpreader.Reader(p_file).geometries())
# Cities/Towns to plot
t_lat = [51.089682, 51.177924, 51.426574, 51.268964, 51.394761]
t_lon = [-115.360909, -115.570507, -116.18042, -115.919495, -116.49353]
t_name = ['Canmore','Banff','Lake Louise','Castle Junction','Field']

# Make fig dir
if not os.path.isdir(fig_dir):
    os.mkdir(fig_dir)

# General plotting functions

# Plot setup
def make_map(projection=ccrs.PlateCarree()):
    fig, ax = plt.subplots(subplot_kw=dict(projection=projection))
    fig.set_size_inches(20, 12)
    #ax.coastlines(resolution='100m', zorder=1)

    gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                       linewidth=2, color='gray', alpha=0.4, linestyle='--')
    gl.xlabels_top = gl.ylabels_right = False
    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER
    gl.xlabel_style = {'size': 'medium'}
    gl.ylabel_style = {'size': 'medium'}

    return fig, ax

def save_figure(f,file_out,fig_res):
    f.savefig(file_out,bbox_inches='tight',dpi=fig_res)

def plot_variable(tri_var, var2plot, time_start, c_timestamp,
                  fig_res, var_vmin, var_vmax, obs_pts, proj_in):
    # Make map
    fig, ax = make_map()

    # Get time stamp as string
    str_timestamp = pd.to_datetime(c_timestamp).strftime('%Y-%m-%d %H:%M:%S MST')
    if time_start:
        str_time_start = pd.to_datetime(time_start).strftime('%Y-%m-%d %H:%M:%S')
    file_timestamp = pd.to_datetime(c_timestamp).strftime('%Y_%m_%d_%H:%M:%S_MST.png')
    
    # Make tri plot
    p1 = ax.tripcolor(tri_info['Lon'], tri_info['Lat'], tri_info['triang'],
                      facecolors=tri_var * scale_factor[var2plot],
                      cmap=cmap_dict[var2plot],
                      vmin= var_vmin * scale_factor[var2plot],
                      vmax= var_vmax * scale_factor[var2plot])
    
    # Add title
    if time_start:
        ax.set_title(title_dict[var2plot] + '.\n' + str_time_start + ' to\n'+str_timestamp + '\n')
    else:
        ax.set_title(title_dict[var2plot]+'.\n'+str_timestamp+'\n')

    # Plot scatter of Obs (if exists)
    if obs_pts is not None:
        if (obs_pts.notnull().sum()>0):
            p2 = ax.scatter(obs_pts.Lon, obs_pts.Lat, s=200,
                        c=obs_pts.values*scale_factor[var2plot], zorder=500,
                        cmap=cmap_dict[var2plot],
                        vmin=var_vmin * scale_factor[var2plot],
                        vmax=var_vmax * scale_factor[var2plot],
                        edgecolors='k', linewidths=2)

    # Add landmarks
    ax.add_geometries(p_sh, ccrs.PlateCarree(),
                       edgecolor='black', facecolor='none', alpha=0.5) #AB/BC boarder
    # Town/Cites
    ax.scatter(t_lon, t_lat, c='k', s=300, marker='*')
    for i, txt in enumerate(t_name):
        ax.annotate(txt, (t_lon[i]+0.01, t_lat[i]+0.01), fontsize=20)

    # Add colorbar
    b1 = fig.colorbar(p1)
    b1.ax.set_ylabel(ylabel_dict[var2plot])

    # Set map extent
    c_extent = [np.min(tri_info['Lon']), np.max(tri_info['Lon']),
                     np.min(tri_info['Lat']), np.max(tri_info['Lat'])]
    ax.set_extent(c_extent, ccrs.PlateCarree())

    # Add legend
    if obs_pts is not None:
        obs_artist = plt.Line2D((0, 1), (0, 0), color='k', marker='o', linestyle='')
        ax.legend([obs_artist], ['Observed'], loc='upper right')

    # Save figure
    if time_start:
        file_out = os.path.join(fig_dir, var2plot + '.png')
    else:
        file_out = os.path.join(fig_dir, var2plot, var2plot+'_'+file_timestamp)
    save_figure(fig, file_out, fig_res)
    return file_out

# Get General info about vtus

# Move to vtu dir
os.chdir(vtu_dir)
# Get list of files
vtu_files = np.sort(glob.glob(prefix+'*.vtu'))
# Get time stamps
time_stamps_all_UTC = vfunc.get_vtu_time(vtu_files, prefix)
# Adjust time zone
time_stamps_all_LST = time_stamps_all_UTC + pd.DateOffset(hours=local_time_offset)
# Create series of time stamps and vtu files
ps = pd.Series(vtu_files, index=time_stamps_all_LST)
# Get mesh
cmesh = vfunc.get_mesh(vtu_files[-1])
# Get tri info
tri_info = vfunc.get_triangle(cmesh)

# Get mesh coords system
if not cmesh.GetFieldData().HasArray("proj4"):
    print("VTU file does not contain a proj4 field")
    sys.exit()
vtu_proj4 = Proj(cmesh.GetFieldData().GetAbstractArray("proj4").GetValue(0))

# Convert mesh to geographic
outProj = Proj(init='epsg:4326')
tri_info['Lon'], tri_info['Lat'] = transform(vtu_proj4, outProj, tri_info['X'], tri_info['Y'])
# Trim OBS to only stations within mesh domain
m_lon_lims = [np.min(tri_info['Lon']), np.max(tri_info['Lon'])]
m_lat_lims = [np.min(tri_info['Lat']), np.max(tri_info['Lat'])]
OBS_data = OBS_data.where( (OBS_data['Lon']>=m_lon_lims[0]) &
                           (OBS_data['Lon']<=m_lon_lims[1]) &
                          (OBS_data['Lat']>=m_lat_lims[0]) &
                           (OBS_data['Lat'] <= m_lat_lims[1]), drop=True)


# # Covert lat/long to porjective coord system of CHM
# outProj = Proj(init='epsg:4326')
# obs_X, obs_Y = transform(outProj, vtu_proj4,OBS_data['Lon'].values, OBS_data['Lat'].values)
# OBS_data.coords['X'] = xr.DataArray(obs_X, coords={'station':OBS_data.station}, dims=['station'])
# OBS_data.coords['Y'] = xr.DataArray(obs_Y, coords={'station':OBS_data.station}, dims=['station'])
# # Trim to only stations within mesh domain
# m_x_lims = [np.min(tri_info['X']), np.max(tri_info['X'])]
# m_y_lims = [np.min(tri_info['Y']), np.max(tri_info['Y'])]
# OBS_data = OBS_data.where( (OBS_data['X']>=m_x_lims[0]) &
#                            (OBS_data['X']<=m_x_lims[1]) &
#                           (OBS_data['Y']>=m_y_lims[0]) &
#                            (OBS_data['Y'] <= m_y_lims[1]), drop=True)

# Correct CHM units
chm_units_fix = {'snowdepthavg':1, 'swe':1.0/1000, 'p_snow':1.0/1000, 'p_rain':1.0/1000} # to m

# Plotting dictionaries
ylabel_dict = {'snowdepthavg':'Snowdepth (cm)','swe':'SWE (mm)', 'p_snow':'Liquid equivalent (mm)', 
                'p_rain':'Rainfall (mm)',
               'snowdepthavg_diff': 'Snowdepth change (cm)', 'swe_diff': 'SWE change (mm)'}
# From meteric (m) to display units
scale_factor = {'snowdepthavg':100,'swe':1000, 'p_snow':1000, 'p_rain':1000,
                'snowdepthavg_diff': 100, 'swe_diff': 1000,}
title_dict = {'snowdepthavg':'Snowdepth','swe':'SWE','p_snow':'Snowfall','p_rain':'Rainfall',
              'snowdepthavg_diff': 'Snowdepth change', 'swe_diff': 'SWE change'}
cmap_dict = {'snowdepthavg':mpl.colors.ListedColormap(sns.color_palette("Blues", 12)),
             'p_rain':mpl.colors.ListedColormap(sns.color_palette("Reds", 12)),
             'p_snow':mpl.colors.ListedColormap(sns.color_palette("Blues", 12)),
             'swe':mpl.colors.ListedColormap(sns.color_palette("Greys", 12)),
             'snowdepthavg_diff': mpl.colors.ListedColormap(sns.color_palette("RdBu", 12)),
             'swe_diff': mpl.colors.ListedColormap(sns.color_palette("RdBu", 12))}
var_min_delta = {'snowdepthavg':0.1,'swe':0.01, 'p_snow':0.01} # Min max value for plotting change (m)


# Make single variable plots
var_names_2_plot = ['snowdepthavg','swe','p_snow']

# Make dirs
for var2plot in var_names_2_plot:
    if not os.path.isdir(os.path.join(fig_dir,var2plot)):
        os.mkdir(os.path.join(fig_dir,var2plot))

# Plot snapshots in time
for var2plot in var_names_2_plot:
    # Get data for all time stamps
    df_cvar = vfunc.get_multi_mesh_var_dask(ps.tail(last_N).values, var2plot, ps.tail(last_N).index)
    df_cvar = df_cvar * chm_units_fix[var2plot] # Units to Metric standard (m)
    # Compute quantile
    df_cvar_max  = np.percentile(df_cvar.values[:], 95)
    print(df_cvar_max)    
    df_cvar_min = 0

    # See if we have obs for this variable
    if var2plot in OBS_data:
        obs_cvar = OBS_data[var2plot]

    for ct in df_cvar.index:
        print('printing ',ct)
        # See if we have any observations for this time step (with some tolerance)
        obs_ct = obs_cvar.sel(time=ct, method='nearest')
        # print(np.abs((obs_ct.time.values-np.datetime64(ct))))
        dt_diff = np.abs((obs_ct.time.values-np.datetime64(ct))) > np.timedelta64(6,'h') # 6 hour tolerance
        noObs = obs_ct.notnull().sum(dim='station')==0
        if dt_diff | noObs:
            obs_ct = None
            print("No Obs within 6 hours OR no non-missing measurements")
        
        # Plot and Save
        file_out = plot_variable(df_cvar.loc[ct].values, var2plot, [], ct,
                                 fig_res, df_cvar_min, df_cvar_max, obs_ct, vtu_proj4)
        print('fig saved')
        
        # If last time
        if ct==df_cvar.index[-1]:
            print('Copied last vtu to '+var2plot+'_most_recent.png')
            shutil.copyfile(file_out, os.path.join(fig_dir,var2plot+'_most_recent.png'))


# Plot change from NOW* to most future forecast
# *NOW is defined as the CHM output time stamp most nearest to the time plot sripts run
time_now = datetime.datetime.now() - datetime.timedelta(hours=1)# Chinook is on CST (-6) need to subtract 1 hour to got MST -7
i = np.argmin(np.abs(ps.index.to_pydatetime() - time_now))
time_now_near = ps.index[i]
time_fut = ps.index[-1]

for var2plot in var_names_2_plot:
    if var2plot in ['p_snow']: # Skip for some variables
        continue
    # Get data for all time stamps
    df_cvar = vfunc.get_multi_mesh_var_dask(ps.loc[[time_now_near, time_fut]].values,
                                            var2plot, ps.loc[[time_now_near, time_fut]].index)
    df_cvar = df_cvar * chm_units_fix[var2plot] # Units to Metric standard (m)
    # Take difference
    df_dif = df_cvar.diff(axis=0).iloc[1] # diff over time, returns missing on first row, so take second
    df_trim = df_dif[np.abs(df_dif-df_dif.mean())<=(3*df_dif.std())] # Remove outliers (sometimes from avalnching)
    df_cvar_max = np.max([np.abs(df_trim.min()), df_trim.max()]) # Use larger of neg or pos values
    df_cvar_max = np.max([df_cvar_max, var_min_delta[var2plot]]) # Min max delta value
    df_cvar_min = -1*df_cvar_max
    print(df_cvar_min, df_cvar_max)
    print('printing ',time_fut,' minus ',time_now_near)
    # Plot and Save
    file_out = plot_variable(df_dif.values, var2plot+'_diff',
                             time_now_near, time_fut, fig_res, df_cvar_min,
                             df_cvar_max, None, vtu_proj4)
    print('fig saved')



#
# import sys
# sys.exit()
# ### OLD FIGURE CODE BELOW
#
# cfile = vtu_files[-1]
#
# # Get time
# time_stamp = vfunc.get_vtu_time([cfile],prefix)
#
# # Adjust time zone
# time_stamp = pd.to_datetime(time_stamp) + datetime.timedelta(hours=local_time_offset)
#
# # Get data
# # Get mesh
# cmesh = vfunc.get_mesh(cfile)
#
# z = vfunc.get_face_var(cmesh,'snowdepthavg')
#
# # Move to fig dir
# os.chdir(fig_dir)
#
# # Plot on map
# fig, ax = make_map()
# #kw = dict(marker='.', linestyle='-', alpha=0.25, color='darkgray', zorder=0)
# #lines = ax.triplot(tri_info['X'], tri_info['Y'], **kw)
# ax.set_title('Snow depth.\n'+pd.to_datetime(time_stamp[0]).strftime('%Y-%m-%d %H:%M:%S MST')+'\n')
# p1 = ax.tripcolor(tri_info['X'], tri_info['Y'], tri_info['triang'],facecolors=z*100,cmap=cmap_dict[var2plot],vmin=0, vmax=np.nanmax(z)*100*0.8) # Max at 80% of mean (helps show small depths)
# b1 = fig.colorbar(p1)
# b1.ax.set_ylabel('Snow depth (cm)')
# gl = ax.gridlines(draw_labels=True)
# gl.xlabels_top = gl.ylabels_right = False
# gl.xformatter = LONGITUDE_FORMATTER
# gl.yformatter = LATITUDE_FORMATTER
#
# #sns.set_palette("BuGn_r")
# fig.savefig('snowdepth_48h.png',bbox_inches='tight',dpi=fig_res)
#
# # Input
# var_name = 'swe'
#
# # Move to vtu dir
# os.chdir(vtu_dir)
# # Get list of files
# vtu_files = np.sort(glob.glob(prefix+'*.vtu'))
# # file to plot
# cfile = vtu_files[-1]
#
# # Get time
# time_stamp = vfunc.get_vtu_time([cfile],prefix)
#
# # Adjust time zone
# time_stamp = pd.to_datetime(time_stamp) + datetime.timedelta(hours=local_time_offset)
#
# # Get data
# # Get mesh
# cmesh = vfunc.get_mesh(cfile)
# swe = vfunc.get_face_var(cmesh,var_name)
# #df_swe = vfunc.get_multi_mesh_var_dask(cfile,var_name,time_stamp)
#
# # Get swe, calc bulk density (kg m^2)
# swe = swe/1000 # mm to m
# bulk_density = swe/z*1000 # fraction to kg m^2
# bulk_density[~np.isfinite(bulk_density)] = 0
#
# # Move to fig dir
# os.chdir(fig_dir)
#
# # Plot on map
# fig2, ax = make_map()
# #kw = dict(marker='.', linestyle='-', alpha=0.25, color='darkgray', zorder=0)
# #lines = ax.triplot(tri_info['X'], tri_info['Y'], **kw)
# ax.set_title('Snow Density.\n '+pd.to_datetime(time_stamp[0]).strftime('%Y-%m-%d %H:%M:%S MST')+'\n')
# p1 = ax.tripcolor(tri_info['X'], tri_info['Y'], tri_info['triang'],facecolors=bulk_density,cmap='Greens', vmin=50, vmax=450)
# b1 = fig2.colorbar(p1)
# b1.ax.set_ylabel('Bulk Density kg/m^3')
# #sns.set_palette("BuGn_r")
# fig2.savefig('density.png',bbox_inches='tight',dpi=fig_res)
#
# ## 48 accumued snow depth
# # Input
# var_name = 'snowdepthavg'
#
# # Move to vtu dir
# os.chdir(vtu_dir)
# # Get list of files
# vtu_files = np.sort(glob.glob(prefix+'*.vtu'))
# # Then get times for ALL files
# time_stamp_all = vfunc.get_vtu_time(vtu_files,prefix)
# # last_time = time_stamp_all[-1]
# t_dt = (time_stamp_all[1]-time_stamp_all[0])
# time_dt_h = t_dt.days * 24 +  t_dt.seconds/3600
# day_before_index = -(1+ int(24/time_dt_h))
#
# # file to plot
# cfile = [vtu_files[day_before_index],vtu_files[-1]]
#
# # Get time
# time_stamp = vfunc.get_vtu_time(cfile,prefix)
#
# # Adjust time zone
# time_stamp = pd.to_datetime(time_stamp) + datetime.timedelta(hours=local_time_offset)
#
# # Get data
# df_snowdepth = vfunc.get_multi_mesh_var_dask(cfile,var_name,time_stamp)
#
# # Take diff in 48 hrs m to cm
# del_snowdepth = df_snowdepth.diff(periods=1,axis=1).ix[:,1]*100
# abs_max = np.max([del_snowdepth.max(), -1*del_snowdepth.min()])
#
# # Move to fig dir
# os.chdir(fig_dir)
#
# # Plot on map
# fig3, ax = make_map()
# #kw = dict(marker='.', linestyle='-', alpha=0.25, color='darkgray', zorder=0)
# #lines = ax.triplot(tri_info['X'], tri_info['Y'], **kw)
# ax.set_title('Snowpack change.\n '+pd.to_datetime(time_stamp[0]).strftime('%Y-%m-%d %H:%M:%S MST')+'\nto '+pd.to_datetime(time_stamp[-1]).strftime('%Y-%m-%d %H:%M:%S'))
# p1 = ax.tripcolor(tri_info['X'], tri_info['Y'], tri_info['triang'],facecolors=del_snowdepth,cmap='seismic_r',vmin=-1*abs_max,vmax=abs_max)
# b1 = fig3.colorbar(p1)
# b1.ax.set_ylabel('delta depth (cm)')
# #sns.set_palette("BuGn_r")
# fig3.savefig('48_snowdepth_change.png',bbox_inches='tight',dpi=fig_res)
#
#
#
# plt.show()
