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

cache = Cache(10e9)
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
    raise ValueError('requires one argument [configuration file] (i.e. python GRIB2_to_CHM_forcing.py forcing_config.py')


# Get name of configuration file/module
configfile = sys.argv[-1]

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
netcdf_dir = X.netcdf_dir
ascii_dir   = X.ascii_dir
Forcing_config_file = X.Forcing_config_file
lat_r = X.lat_r
lon_r = X.lon_r
local_time_offset = X.local_time_offset
coordsystem = X.coordsystem
if coordsystem=='pro':
    utm_zone = X.utm_zone


# Move to input
os.chdir(netcdf_dir)

# Get all file names
all_files =  sorted(glob.glob('*.nc'))

first_day = True # Flag to write header to csv files if first month

# Move to ascii dir
if not os.path.isdir(ascii_dir):
    os.mkdir(ascii_dir)


for cd in all_files:
    flag1 = False # flag to check we are not missing a forecast
    print cd

    # Load current file
    os.chdir(netcdf_dir)
    ds = xr.open_dataset(cd,engine='netcdf4')

    # Select only times we want
    # If so grab 48hr forecast
    if (cd==all_files[-1]):
        ds = ds.isel(datetime=np.arange(6,48))
    # Otherwise only grab the 24 hours
    else:
        ds = ds.isel(datetime=np.arange(6,30))

    # Apply a bias correction (optional)
    #ds['Qli'] = ds.Qli + 30
    #print "Warning, applying +30 ilwr bias correctoin"

    ## Adjust to local time zone (i.e. from UTC to MST, local_time_offset should = -7)
    #ds['datetime'] = pd.to_datetime(ds.datetime.values) + datetime.timedelta(hours=local_time_offset)

    # Move to ascii dir
    os.chdir(ascii_dir)

    print 'Extracting cells within lat/long box'
    ds = ds.where((ds.gridlat_0>lat_r[0]) & (ds.gridlat_0<lat_r[1]) & (ds.gridlon_0>lon_r[0]) &
                  (ds.gridlon_0<lon_r[1]), drop=True)
    # Get small dataset of lat and long
    grid = ds[['gridlat_0', 'gridlon_0','HGT_P0_L1_GST0']]

    # Initalize dictionary of metadata
    meta = {}

    # Loop through each point within our lat long box
    for i in range(ds.coords['xgrid_0'].size):
        for j in range(ds.coords['ygrid_0'].size):
            sub_grid = grid.isel(xgrid_0=i, ygrid_0=j)
            if ((sub_grid.gridlat_0>lat_r[0]) & (sub_grid.gridlat_0<lat_r[1]) & (sub_grid.gridlon_0>lon_r[0]) & (sub_grid.gridlon_0<lon_r[1])):
                # Select point
                sub_ds = ds.isel(xgrid_0=i, ygrid_0=j)
                # Convert to dataframe
                df = sub_ds.to_dataframe()

                def drop_possible_var(var_in,df):
                    if var_in in df:
                        return df.drop(var_in,axis=1)
                    else:
                        return df
                for cdropVar in ['HGT_P0_L1_GST0','xgrid_0','ygrid_0','gridlat_0','gridlon_0']:
                    df = drop_possible_var(cdropVar,df)
                # Drop unwanted vars/coords
                # df.drop(['HGT_P0_L1_GST0','xgrid_0','ygrid_0','gridlat_0','gridlon_0'], axis=1, inplace=True)
                # df.drop(['xgrid_0', 'ygrid_0'], axis=1, inplace=True)

                if first_day:
                    # Write to ascii CHM format
                    of = open('point_'+str(i)+'_'+str(j)+'.chm','w')
                    df.to_csv(of,sep='\t',date_format='%Y%m%dT%H%M%S')
                    of.close()
                    df = None

                    # Build list of point metadata
                    coords = []
                    if coordsystem=='geo':
                        coords.append(float(sub_grid.gridlon_0.values))
                        coords.append(float(sub_grid.gridlat_0.values))
                    elif coordsystem=='pro':
                        coords = utm.from_latlon(sub_grid.gridlat_0,sub_grid.gridlon_0, utm_zone)
                    else:
                        print 'Unknown coords = ' + coordsystem

                    meta['point_'+str(i)+'_'+str(j)] = {'file':ascii_dir+'/point_'+str(i)+'_'+str(j)+'.chm',
                    "longitude":coords[0],
                    "latitude":coords[1],
                    "elevation":sub_grid.HGT_P0_L1_GST0.values[0],
                    "filter": {
                    "scale_wind_speed": {
                    "variable": "u",
                    "Z_F": 10
                     }}}
                else:
                    # Write to ascii CHM format
                    of = open('point_'+str(i)+'_'+str(j)+'.chm','a')
                    if not flag1: # if we haven't checked yet (first station)
                        # Check last time steps line up
                        old_df = pd.read_csv('point_'+str(i)+'_'+str(j)+'.chm',sep="\t",parse_dates=True)
                        wantTime = pd.to_datetime(old_df['datetime'].iloc[-1]) + datetime.timedelta(hours=1)
                        if not (wantTime==pd.to_datetime(df.index[0])):
                            print 'Missing time steps for file'
                            print 'Wanted ' + str(wantTime)
                            print 'Got ' + str(df.index[0])
                            sys.exit()
                    flag1 = True

                    df.to_csv(of,sep='\t',date_format='%Y%m%dT%H%M%S', mode='a', header=False)
                    of.close()
                    df = None

                # Clean up memory
            sub_grid = None

    # Continue of current day
    if first_day:
        # Write out json file with metadata for these points
        print("Writing out GEM forcing json file")
        with open(Forcing_config_file, 'w') as outfile:
            json.dump(meta, outfile,indent=4, sort_keys=True)

    # End of current month
    first_day = False

print("--- %s minutes ---" % ((time.time() - start_time)/60))
print 'finished!'
