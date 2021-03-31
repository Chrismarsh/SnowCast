import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.io.shapereader as shpreader
import matplotlib.ticker as mticker
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
import xarray as xr
import seaborn as sns
import sys
import os
import imp
import CHM_functions as chmF

# Load in config file
'''  load user configurable paramters here    '''
# Check user defined configuraiton file
if len(sys.argv) == 1:
    sys.exit('Requires one argument [configuration file]')

# Get name of configuration file/module
configfile = sys.argv[-1]

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
data_dir = X.data_dir
git_dir = X.git_dir

fig_dir = os.path.join(git_dir , 'In_Situ_Data', 'figures')
fig_res = 300 # dpi

# Make fig dir
if not os.path.isdir(fig_dir):
    os.mkdir(fig_dir)

###################################
# Load data in
###################################

# File paths
file_in = os.path.join(data_dir, 'QC', 'Hourly_QC.nc') # CRHO and other data
snow_survey_in  = os.path.join(data_dir, 'CRHO_HIST', 'netcdf', 'CRHO_Snow_Survey_Individual.nc')
EC_snow_course_in = os.path.join(data_dir, 'EC_Snow_Courses', 'netcdf', 'EC_Snow_Courses.nc')
dem_file = os.path.join(data_dir, 'Static_data', 'SnowCast.tif')
p_file = os.path.join(data_dir, 'Static_data', 'CAN_adm1.shp')

# Load all obs
ds = xr.open_dataset(file_in, engine='netcdf4') #.load()

# Snow surveys
SS_data = xr.open_dataset(snow_survey_in,engine='netcdf4')
EC_data = xr.open_dataset(EC_snow_course_in)

# Load in dem
dem = xr.open_rasterio(dem_file).sel(band=1).drop('band')
# Provences
p_sh = list(shpreader.Reader(p_file).geometries())

# Cities/Towns to plot
t_lat = [51.089682, 51.177924, 51.426574, 51.268964, 51.394761]
t_lon = [-115.360909, -115.570507, -116.18042, -115.919495, -116.49353]
t_name = ['Canmore','Banff','Lake Louise','Castle Junction','Field']

dem_file_big = r'F:\Work\e\Data\DEMs\NA.tif'
dem_big = xr.open_rasterio(dem_file_big).sel(band=1).drop('band')

# Trim down ds (its big)
ds = ds[['SnowDepthA']]
# ds = ds.coords

lat_r = ds.Lat.max()-ds.Lat.min()
lon_r = ds.Lon.max()-ds.Lon.min()
bdy = 0.2
box = [ds.Lon.min()-lon_r*bdy, ds.Lon.max()+lon_r*bdy, ds.Lat.min()-lat_r*bdy, ds.Lat.max()+lat_r*bdy]

# Set nan in dem
dem = dem.where(dem>0)
dem = dem.where((dem.x>box[0]) & (dem.x<box[1]) & (dem.y>box[2]) & (dem.y<box[3]), drop=True)

dem_big = dem_big.where(dem_big>0)
dem_big = dem_big.where((dem_big.x>box[0]) & (dem_big.x<box[1]) & (dem_big.y>box[2]) & (dem_big.y<box[3]), drop=True)


p_sh = list(shpreader.Reader(p_file).geometries())

cmap_elev = mpl.colors.ListedColormap(sns.color_palette("Greys", 10))
cmap_network = {b'bcRiverForecastCenter':'r', b'environmentAlberta':'k',b'CRHO':'b',b'ABE_AGG_HIST':'g'} # byte is needed for 3.5
legend_network = {b'bcRiverForecastCenter':'BC River Forecast Center',
                  b'environmentAlberta':'Alberta Environment snow', b'CRHO':'Canadian Rockies Hydrological Observatory',
                  b'ABE_AGG_HIST':'Alberta Environment &\nAlberta Agriculture and Forestry'} # byte is needed for 3.5

# sns.set_style('whitegrid')
# sns.set_context("talk", font_scale=2, rc={"lines.linewidth": 2})

# Cities/Towns to plot
t_lat = [51.089682, 51.177924, 51.426574, 51.268964, 51.394761]
t_lon = [-115.360909, -115.570507, -116.18042, -115.919495, -116.49353]
t_name = ['Canmore','Banff','Lake Louise','Castle Junction','Field']



# PLot map of all stations
fig = plt.figure(figsize=(20, 20))
ax1 = plt.axes(projection=ccrs.AlbersEqualArea())
# ax1.set_extent(box)
ax1.imshow(np.flipud(dem_big.values), extent=[np.min(dem_big.x), np.max(dem_big.x),
                                             np.min(dem_big.y), np.max(dem_big.y)], aspect=ax1.get_aspect())
# ax1.set_title('Elevation')
for c_net in set(ds.network.values):
    lat_pts = ds.Lat.sel(staID=(ds.where(ds.network==c_net, drop=True).network).staID).values
    lon_pts = ds.Lon.sel(staID=(ds.where(ds.network==c_net, drop=True).network).staID).values
    I_not_nan = ~np.isnan(lat_pts) & ~np.isnan(lon_pts)
    lat_pts = lat_pts[I_not_nan]
    lon_pts = lon_pts[I_not_nan]
    
    ax1.scatter(lon_pts, lat_pts, transform=ccrs.AlbersEqualArea(), s=50, c=cmap_network[c_net], zorder=100, label=c_net) #yc, xc -- lists or numpy arrays

# Snow Courses
lat_pts = EC_data.Lat.values
lon_pts = EC_data.Lon.values
I_not_nan = ~np.isnan(lat_pts) & ~np.isnan(lon_pts)
lat_pts = lat_pts[I_not_nan]
lon_pts = lon_pts[I_not_nan]

ax1.scatter(lon_pts, lat_pts, transform=ccrs.AlbersEqualArea(), marker='o', s=50, c='m', zorder=200, label='EC Snow Course') #yc, xc -- lists or numpy arrays

    
ax1.add_geometries(p_sh, ccrs.AlbersEqualArea(),
                  edgecolor='black', facecolor='none', alpha=0.5)
plt.legend()



''' Subset observation data to CRHO domain'''
ds_crho = ds.where((ds.Lat >= np.min(dem.y)) & (ds.Lat <= np.max(dem.y))
                   &(ds.Lon >= np.min(dem.x)) &(ds.Lon <= np.max(dem.x)), drop=True)
EC_data_crho = EC_data.where((EC_data.Lat >= np.min(dem.y)) & (EC_data.Lat <= np.max(dem.y))
                   &(EC_data.Lon >= np.min(dem.x)) &(EC_data.Lon <= np.max(dem.x)), drop=True )
# Plot map of SnowCast domain
fig2 = plt.figure(figsize=(20, 20))
ax1 = plt.axes(projection=ccrs.PlateCarree())
# ax1.set_extent(box)
ax1.imshow(np.flipud(dem.values), extent=[np.min(dem.x), np.max(dem.x),
                                             np.min(dem.y), np.max(dem.y)], aspect=ax1.get_aspect())
# ax1.set_title('Elevation')
for c_net in set(ds_crho.network.values):
    lat_pts = ds_crho.Lat.sel(staID=(ds_crho.where(ds_crho.network==c_net, drop=True).network).staID).values
    lon_pts = ds_crho.Lon.sel(staID=(ds_crho.where(ds_crho.network==c_net, drop=True).network).staID).values
    I_not_nan = ~np.isnan(lat_pts) & ~np.isnan(lon_pts)
    lat_pts = lat_pts[I_not_nan]
    lon_pts = lon_pts[I_not_nan]

    ax1.scatter(lon_pts, lat_pts, transform=ccrs.PlateCarree(), s=100,
                c=cmap_network[c_net], zorder=100, label=legend_network[c_net]) #yc, xc -- lists or numpy arrays
# Snow Courses
lat_pts = EC_data_crho.Lat.values
lon_pts = EC_data_crho.Lon.values
I_not_nan = ~np.isnan(lat_pts) & ~np.isnan(lon_pts)
lat_pts = lat_pts[I_not_nan]
lon_pts = lon_pts[I_not_nan]
ax1.scatter(lon_pts, lat_pts, transform=ccrs.PlateCarree(), marker='o', s=100,
            c='m', zorder=200, label='Alberta Environment Snow Course') #yc, xc -- lists or numpy arrays
ax1.add_geometries(p_sh, ccrs.PlateCarree(),
                  edgecolor='black', facecolor='none', alpha=0.5)
# Town/Cites
ax1.scatter(t_lon, t_lat, c='k', s=300, marker='*')
for i, txt in enumerate(t_name):
    ax1.annotate(txt, (t_lon[i]+0.01, t_lat[i]+0.01), fontsize=20)
leg = plt.legend(fancybox=True, loc='lower left', frameon=True, fontsize='xx-large', bbox_to_anchor=(-0.009, -0.009))
leg.get_frame().set_facecolor('#ffffff')
leg.get_frame().set_alpha(0.75)

gl = ax1.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                  linewidth=2, color='gray', alpha=0.5, linestyle='--')
gl.xformatter = LONGITUDE_FORMATTER
gl.yformatter = LATITUDE_FORMATTER
gl.xlabel_style = {'size': 'x-large'}
gl.ylabel_style = {'size': 'x-large'}

# Save Figure
file_out = os.path.join(fig_dir, 'CRHO_station_map.png')
chmF.save_figure(fig2, file_out, fig_res)

plt.show()

#
#
# fig = plt.figure(figsize=(20, 10))
# ax1 = plt.axes(projection=ccrs.AlbersEqualArea())
# # ax1.set_extent(box)
# ax1.imshow(np.flipud(dem.values), extent=[np.min(dem.x), np.max(dem.x),
#                                              np.min(dem.y), np.max(dem.y)], aspect=ax1.get_aspect())
#
# swe_max = ds.SnowWaterEquivelentA.max(dim='Time_UTC')
# lat_pts = swe_max.Lat.values
# lon_pts = swe_max.Lon.values
#
# I_not_nan = ~np.isnan(lat_pts) & ~np.isnan(lon_pts) & ~np.isnan(swe_max.values)
# lat_pts = lat_pts[I_not_nan]
# lon_pts = lon_pts[I_not_nan]
# c_swe   = swe_max[I_not_nan].values
# cmapblues = mpl.colors.ListedColormap(sns.color_palette("Reds", 10))
#
#
# p1 = ax1.scatter(lon_pts, lat_pts, transform=ccrs.AlbersEqualArea(), s=50, c=c_swe, cmap=cmapblues, zorder=100) #yc, xc -- lists or numpy arrays
#
# ax1.add_geometries(p_sh, ccrs.AlbersEqualArea(),
#                   edgecolor='black', facecolor='none', alpha=0.5)
# c0 = fig.colorbar(p1, ax=ax1, orientation="vertical", label='Peak SnowWaterEquivelentA (m)')
#
#
# fig = plt.figure(figsize=(20, 10))
# ax1 = plt.axes(projection=ccrs.AlbersEqualArea())
# # ax1.set_extent(box)
# ax1.imshow(np.flipud(dem.values), extent=[np.min(dem.x), np.max(dem.x),
#                                              np.min(dem.y), np.max(dem.y)], aspect=ax1.get_aspect())
#
# swe_mean = ds.SnowWaterEquivelentA.mean(dim='Time_UTC')
# swe_mean = swe_mean.where((swe_mean.Lat>50.7467287151959) & (swe_mean.Lat<51.2770940589401) &
#                           (swe_mean.Lon>-119.135830621329) & (swe_mean.Lon<-113.917157809765), drop=True)
# lat_pts = swe_mean.Lat.values
# lon_pts = swe_mean.Lon.values
#
# I_not_nan = ~np.isnan(lat_pts) & ~np.isnan(lon_pts) & ~np.isnan(swe_mean.values)
# lat_pts = lat_pts[I_not_nan]
# lon_pts = lon_pts[I_not_nan]
# c_swe   = swe_mean[I_not_nan].values
# cmapblues = mpl.colors.ListedColormap(sns.color_palette("Reds", 10))
#
#
# p1 = ax1.scatter(lon_pts, lat_pts, transform=ccrs.AlbersEqualArea(), s=50, c=c_swe, cmap=cmapblues, zorder=100) #yc, xc -- lists or numpy arrays
#
# ax1.add_geometries(p_sh, ccrs.AlbersEqualArea(),
#                   edgecolor='black', facecolor='none', alpha=0.5)
# c0 = fig.colorbar(p1, ax=ax1, orientation="vertical", label='Mean SnowWaterEquivelentA (m)')
# print(swe_mean.min().values)
# print(swe_mean.mean().values)
# print(swe_mean.max().values)
#
#
# X = ds.SnowWaterEquivelentA.where((swe_mean.Lat>50.7467287151959) & (swe_mean.Lat<51.2770940589401) &
#                           (swe_mean.Lon>-119.135830621329) & (swe_mean.Lon<-113.917157809765), drop=True)
#
#
# plt.figure()
# for staID in X.staID:
#     if X.sel(staID=staID).sum() > 0:
#         plt.plot(ds.Time_UTC, X.sel(staID=staID), label=staID.station_name.values)
# plt.legend()






# In[ ]:



