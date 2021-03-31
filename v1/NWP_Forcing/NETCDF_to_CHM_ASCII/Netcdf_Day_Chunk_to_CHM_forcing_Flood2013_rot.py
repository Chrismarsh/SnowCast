import xarray as xr
import os
import glob
import imp
import sys
import numpy as np
import pandas as pd
import datetime
import json
import time
import utm
import pdb
###
# Experimental cache option to speed up dask calls
# import cachey
# from dask.cache import Cache
# cache = Cache(10e9)
# cache.register()
###
start_time = time.time()
# Hack to force datetimes to display in GMT/UTC (numpy 1.11.1 has fixed this but other dependent modules (pynio) can't handel numpy 1.11.1)
os.environ['TZ'] = 'GMT'
time.tzset()


def drop_possible_var(var_in, c_df):
    ''' Drop possible variables in dataframes'''
    if var_in in c_df:
        return c_df.drop(var_in, axis=1)
    else:
        return c_df

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) == 1:
    sys.error('requires one argument [configuration file] (i.e. python GRIB2_to_CHM_forcing.py forcing_config.py')

# Get name of configuration file/module
configfile = sys.argv[-1]

# Load in configuration file as module
X = imp.load_source('',configfile)

output_dt = 1 # Hours

# Assign to local variables
netcdf_dir = X.netcdf_dir
ascii_dir   = X.ascii_dir
Forcing_config_file = X.Forcing_config_file
lat_r = X.lat_r
lon_r = X.lon_r
var_dic = X.var_dic
local_time_offset = X.local_time_offset
coordsystem = X.coordsystem
if coordsystem=='pro':
    utm_zone = X.utm_zone

# Move to input
os.chdir(netcdf_dir)

# Get all file names
all_files =  sorted(glob.glob('GEM*snowcast_*.nc'))

first_day = True # Flag to write header to csv files if first month

# Move to ascii dir
if not os.path.isdir(ascii_dir):
    os.mkdir(ascii_dir)

list_var_ave = ['t','press','rh','Qsi','Qli','uu','vv']



for cd in all_files:

    flag1 = False # flag to check we are not missing a forecast
    print cd

    # Load current file
    os.chdir(netcdf_dir)
    ds = xr.open_dataset(cd,engine='netcdf4')

    # Rename variables
    # Allow skip if variable is missing
    ds.rename(var_dic, inplace=True)

    print 'Converting units to CHM units'
    ##### Convert units to CHM requirements

    # longitude
    ds['lon_0'] =  ds.lon_0 - 360.0

    # Drop sigma dims
    ds = ds.isel(zaxis=0).drop('zaxis')
    ds = ds.isel(height=0).drop('height')

    # Relative humidity
    ds['rh'] = ds.rh*100 # fraction to %

    # Pressure (after RH calcs)
    ds['press'] = ds['press'] # Appears to b in hPa already

    # Precipitation (liquid and solid) accumulated (m) to incremental (mm)
    ds['p'] = ds.PR.diff(dim='time', label='lower') * 1000
    
    #Compute zonal and meridonial component of wind vector
    ds['uu'] = ds.u *(np.sin(ds.vw_dir * np.pi/180))
    ds['vv'] = ds.u *(np.cos(ds.vw_dir * np.pi/180))

    # Geopotential to height
    if 'ME' in ds:
        ds['HGT_surface'] = ds.ME
    elif 'GZ' in ds: # Some files are missing GZ (fine as long as its not the first one!)
        ds['HGT_surface'] = ds.GZ * 9.81

    # Rename time
    ds.rename({'time':'datetime'},inplace=True)

    #Update original instantaneous values with time averaged values
    ds_p1 = ds.copy()
    ds_p1['datetime'] = pd.to_datetime(ds_p1.datetime.values) - datetime.timedelta(hours=1)
    ds_avg = (ds+ds_p1)/2 
    pdb.set_trace()
    for var in list_var_ave:
        ds[var] = ds_avg[var]

    # Compute average wind speed and direction from meridonial and zonal wind
    ds['vw_dir'] = np.arctan2(ds.uu, ds.vv) * 180/np.pi
    ds['vw_dir'] = (360 + ds['vw_dir']) % 360   
    ds['u'] = np.sqrt(ds.vv**2.+ds.uu**2.) 

    #Drop variables not necessary for CHM
    ds=ds.drop(['uu','vv','TD','FSF','PR','RN','ME','GZ','HU'])
 
    # Select only times we want
    ds = ds.isel(datetime=np.arange(6,18))
    
    # Move to ascii dir
    os.chdir(ascii_dir)

    print 'Extracting cells within lat/long box'
    ds = ds.where((ds.lat_0>lat_r[0]) & (ds.lat_0<lat_r[1]) &
                  (ds.lon_0>lon_r[0]) &
                  (ds.lon_0<lon_r[1]), drop=True)
    # # Get small dataset of lat and long
    # grid = ds[['lat_0', 'lon_0','HGT_surface']]


    # Initalize dictionary of metadata
    meta = {}

    # Loop through each point within our lat long box


    for i in range(ds.coords['x'].size):
        for j in range(ds.coords['y'].size):
            sub_grid = ds.isel(x=i, y=j)
            if sub_grid.t.notnull().sum()==0:
                continue
            df = sub_grid.to_dataframe()


            for cdropVar in ['HGT_surface','lat_0','lon_0']:
                df = drop_possible_var(cdropVar,df)

            if first_day:
                # Write to ascii CHM format
                of = open('point_'+str(i)+'_'+str(j)+'.chm','w')
                df.to_csv(of,sep='\t',date_format='%Y%m%dT%H%M%S')
                of.close()
                df = None

                # Build list of point metadata
                coords = []
                if coordsystem=='geo':
                    coords.append(float(sub_grid.lon_0.values))
                    coords.append(float(sub_grid.lat_0.values))
                elif coordsystem=='pro':
                    coords = utm.from_latlon(sub_grid.lat_0,sub_grid.lon_0, utm_zone)
                else:
                    print 'Unknown coords = ' + coordsystem

                meta['point_'+str(i)+'_'+str(j)] = {'file':ascii_dir+'/point_'+str(i)+'_'+str(j)+'.chm',
                "longitude":coords[0],
                "latitude":coords[1],
                "elevation":float(sub_grid.HGT_surface.values[0]),
                "filter": {
                "scale_wind_speed": {
                "variable": "u",
                "Z_F": 10
                 }}}
            else:
                # Write to ascii CHM format
                of = open('point_'+str(i)+'_'+str(j)+'.chm','a')
                # if not flag1: # if we haven't checked yet (first station)
                #     # Check last time steps line up
                #     old_df = pd.read_csv('point_'+str(i)+'_'+str(j)+'.chm',sep="\t",parse_dates=True)
                #     wantTime = pd.to_datetime(old_df['datetime'].iloc[-1]) + datetime.timedelta(hours=output_dt)
                #     if not (wantTime==pd.to_datetime(df.index[0])):
                #         print 'Missing time steps for file'
                #         print 'Wanted ' + str(wantTime)
                #         print 'Got ' + str(df.index[0])
                #         sys.exit()
                # flag1 = True

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
