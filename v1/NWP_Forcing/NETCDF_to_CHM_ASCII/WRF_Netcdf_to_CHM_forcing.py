###
# Experimental cache option to speed up dask calls
import cachey
import datetime
import glob
import imp
import json
import numpy as np
import os
import pandas as pd
import sys
import time
import utm
import xarray as xr
from dask.cache import Cache

cache = Cache(4e9)
cache.register()
###
start_time = time.time()
# Hack to force datetimes to display in GMT/UTC (numpy 1.11.1 has fixed this but other dependent modules (pynio) can't handel numpy 1.11.1)
os.environ['TZ'] = 'GMT'
time.tzset()

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) == 1:
    raise ValueError('Netcdf_to_CHM_forcing.py requires one argument [configuration file] (i.e. python GRIB2_to_CHM_forcing.py forcing_config.py')


# Get name of configuration file/module
configfile = sys.argv[-1]

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
netcdf_dir = X.netcdf_dir
ascii_dir   = X.ascii_dir
netcdf_const_dir = X.netcdf_const_dir
Forcing_config_file = X.Forcing_config_file
var_dic = X.var_dic
lat_r = X.lat_r
lon_r = X.lon_r
local_time_offset = X.local_time_offset
coordsystem = X.coordsystem
if coordsystem=='pro':
    utm_zone = X.utm_zone

# Move to input
os.chdir(netcdf_dir)

# Get all file names
all_files =  glob.glob('wrf*')

# Sort file names (open_mfdataset _should_ handle this, but this is a hack to put in correct order)
all_files = sorted(all_files)

# Load all hourly WRF files
ds_in = xr.open_mfdataset(all_files[0:1000],concat_dim='Time',engine='netcdf4')

# Load constant WRF vars
ds_cons = xr.open_dataset(netcdf_const_dir,engine='netcdf4')

# Add Lat long Hgt to ds
lat = ds_cons.XLAT.squeeze(dim='Time')
lat.name = 'lat'
lon = ds_cons.XLONG.squeeze(dim='Time')
lon.name = 'lon'
hgt = ds_cons.HGT.squeeze(dim='Time')
hgt.name = 'hgt'
# Merge into ds
ds = xr.merge([ds_in,lat,lon,hgt])
# Grab cos/sin-alpha (have to reindex to make it shaped like ds)
print "Padding alpha values..."
cosalpha = ds_cons.COSALPHA.reindex_like(ds,method='pad')
sinalpha = ds_cons.SINALPHA.reindex_like(ds,method='pad')
print "Done."
# Clear memory
ds_cons=None

# Rename variables
ds.rename(var_dic,inplace=True)

print 'Loading Dataset into memory!'
ds.load()
print 'Converting units to CHM units'
##### Convert units to CHM requirements

# Air temperature
t_C = ds.t - 273.15
t_C.name = 't'

# Pressure
Press_hPa = ds['press'] / 100 # Pa to hPa
Press_hPa.name = 'press'

# Relative humidity (Based on Tetens' formula (1930))
es = 610.8 * np.exp( (17.27*t_C) / (237.30 + t_C) ) # Pa
RH = (ds.Q2 * ds.press)/(es * (0.622 + ds.Q2*(1.-0.622))) * 100 # %
RH.name = 'rh'

# Wind speed and direction
print "Calculating rotated winds..." 
u_earth = ds.U10*cosalpha - ds.V10*sinalpha
v_earth = ds.V10*cosalpha + ds.U10*sinalpha
u = np.sqrt(u_earth*u_earth+v_earth*v_earth) 
vw_dir = np.arctan2(-1*u_earth,-1*v_earth) * (180/np.pi) + 180
u.name = 'u'
vw_dir.name = 'vw_dir'
print "...Done."

# Merge new vars together
ds_new = xr.merge([ds.lat,ds.lon,ds.hgt,ds.Times,RH,u,vw_dir,Press_hPa,t_C,ds.p,ds.Qli,ds.Qsi,ds.albedo,ds.latentHeat,ds.heatflux,ds.SNOW])

# Build a function to go from numpy.bytes_ to a string - WRF files were compressed
def decode(d):
    decoded = datetime.datetime.strptime(d.decode(encoding='UTF-8'),  "%Y-%m-%d_%H:%M:%S")
    return decoded

dates = ds_new.Times.to_series().apply(decode)
ds_new['Time'] = xr.DataArray.from_series(dates).values
ds_new.rename({'Time':'datetime'},inplace=True)

# Adjust to local time zone (i.e. from UTC to MST, local_time_offset should = -7)
ds_new['datetime'] = pd.to_datetime(ds_new.datetime.values) + datetime.timedelta(hours=local_time_offset)

# Move to ascii dir
if not os.path.isdir(ascii_dir):
    os.mkdir(ascii_dir)
os.chdir(ascii_dir)

# Extract grid cells we want to export
print 'Extracting cells within lat/long box'
ds_new = ds_new.where((ds_new.XLAT>lat_r[0]) & (ds_new.XLAT<lat_r[1]) & (ds_new.XLONG>lon_r[0]) & (ds_new.XLONG<lon_r[1]), drop=True)
#ds_cons = ds_cons.where((ds_cons.XLAT>lat_r[0]) & (ds_cons.XLONG<lat_r[1]) & (ds_cons.XLONG>lon_r[0]) & (ds_cons.XLONG<lon_r[1]), drop=True)

# Get small dataset of lat and long
grid = ds_new[['XLAT', 'XLONG','hgt']]

# Initalize dictionary of metadata
meta = {}

# Loop through each point within our lat long box
i_range = range(ds_new.coords['west_east'].size)
j_range = range(ds_new.coords['south_north'].size)
print "Found " + str(ds_new.coords['west_east'].size) + "i and " + str(ds_new.coords['south_north'].size) + "j cells."
for i in i_range:
    for j in j_range:	
	sub_grid = grid.isel(west_east=i, south_north=j)
        # Check if in domain
	if ((sub_grid.XLAT>lat_r[0]) & (sub_grid.XLAT<lat_r[1]) & (sub_grid.XLONG>lon_r[0]) & (sub_grid.XLONG<lon_r[1])):	
            print "processing point " + str(i) + " " + str(j)
	    # Select point
	    sub_ds = ds_new.isel(west_east=i, south_north=j)
            # Convert to dataframe
	    df = sub_ds.to_dataframe()
	    # Drop unwanted vars/coords 
            df.drop(['Times','south_north','west_east','lat','lon','hgt','XLAT','XLONG'], axis=1, inplace=True)
	    # Write to ascii CHM format
 	    df.to_csv('point_'+str(i)+'_'+str(j)+'.chm',sep='\t',date_format='%Y%m%dT%H%M%S')
	    # Build dicting.json',cnary of point metadata
	    coords = []
	    if coordsystem=='geo':
		coords.append(float(sub_grid.XLONG.values))
	 	coords.append(float(sub_grid.XLAT.values))
	    elif coordsystem=='pro':
	    	coords = utm.from_latlon(sub_grid.XLAT,sub_grid.XLONG, utm_zone)
            else:
		print 'Unknown coords = ' + coordsystem

	    meta['point_'+str(i)+'_'+str(j)] = {'file':ascii_dir+'/point_'+str(i)+'_'+str(j)+'.chm',
		"longitude":coords[0],
		"latitude":coords[1],
		"elevation":sub_grid.hgt.data.tolist(),
		"filter": {
        	"scale_wind_speed": {
          	"variable": "u",
          	"Z_F": 10
        	}}}

# Write out json file with metadata for these points
print("Writing out WRF forcing json file")
with open(Forcing_config_file, 'w') as outfile:
    json.dump(meta, outfile,indent=4, sort_keys=True)

print("--- %s minutes ---" % ((time.time() - start_time)/60))


print 'finished!'
