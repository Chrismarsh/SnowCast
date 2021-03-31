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

start_time = time.time()
# Hack to force datetimes to display in GMT/UTC (numpy 1.11.1 has fixed this but other dependent modules (pynio) can't handel numpy 1.11.1)
os.environ['TZ'] = 'GMT'
time.tzset()

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) == 1:
    raise ValueError('GRIB2_to_CHM_forcing.py requires one argument [configuration file] (i.e. python GRIB2_to_CHM_forcing.py forcing_config.py')


# Get name of configuration file/module
configfile = sys.argv[-1]

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assinge to local variables
netcdf_file = X.netcdf_file
ascii_dir   = X.ascii_dir
Forcing_config_file = X.Forcing_config_file
lat_r = X.lat_r
lon_r = X.lon_r
local_time_offset = X.local_time_offset
coordsystem = X.coordsystem
if coordsystem=='pro':
    utm_zone = X.utm_zone

ds = xr.open_dataset(netcdf_file,engine='netcdf4')

# Adjust to local time zone (i.e. from UTC to MST, local_time_offset should = -7)
ds['datetime'] = pd.to_datetime(ds.datetime.values) + datetime.timedelta(hours=local_time_offset)

# Move to ascii dir
if not os.path.isdir(ascii_dir):
    os.mkdir(ascii_dir)
os.chdir(ascii_dir)

# Extract grid cells we want to export
print 'Extracting cells within lat/long box'
ds = ds.where((ds.latitude>lat_r[0]) & (ds.latitude<lat_r[1]) & (ds.longitude>lon_r[0]) & (ds.longitude<lon_r[1]), drop=True)

# Get small dataset of lat and long
grid = ds[['latitude', 'longitude','elevation']]

# Initalize dictionary of metadata
meta = {}

# Loop through each point within our lat long box
for i in range(ds.coords['x'].size):
    for j in range(ds.coords['y'].size):
	sub_grid = grid.isel(x=i, y=j)
        # Is this test needed here???
	if ((sub_grid.latitude>lat_r[0]) & (sub_grid.latitude<lat_r[1]) & (sub_grid.longitude>lon_r[0]) & (sub_grid.longitude<lon_r[1])):	
	    # Select point
	    sub_ds = ds.isel(x=i, y=j)
            # Convert to dataframe
	    df = sub_ds.to_dataframe()
	    # Drop unwanted vars/coords 
            df.drop(['elevation','x','y','latitude','longitude'], axis=1, inplace=True)
	    # Write to ascii CHM format
 	    df.to_csv('point_'+str(i)+'_'+str(j)+'.chm',sep='\t',date_format='%Y%m%dT%H%M%S')
	    # Build dicting.json',cnary of point metadata
	    coords = []
	    if coordsystem=='geo':
		coords.append(float(sub_grid.longitude.values))
	 	coords.append(float(sub_grid.latitude.values))
	    elif coordsystem=='pro':
	    	coords = utm.from_latlon(sub_grid.latitude,sub_grid.longitude, utm_zone)
            else:
		print 'Unknown coords = ' + coordsystem

	    meta['point_'+str(i)+'_'+str(j)] = {'file':ascii_dir+'/point_'+str(i)+'_'+str(j)+'.chm',
		"longitude":coords[0],
		"latitude":coords[1],
		"elevation":sub_grid.elevation.values.tolist(),
		"filter": {
        	"scale_wind_speed": {
          	"variable": "u",
          	"Z_F": 10
        	}}}

# Write out json file with metadata for these points
print("Writing out CHM forcing json file")
with open(Forcing_config_file, 'w') as outfile:
    json.dump(meta, outfile,indent=4, sort_keys=True)

print("--- %s minutes ---" % ((time.time() - start_time)/60))


print 'finished!'
