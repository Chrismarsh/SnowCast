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
    raise ValueError('requires one argument [configuration file] (i.e. python GRIB2_to_CHM_forcing.py forcing_config.py')

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
all_files =  sorted(glob.glob('GEM_rockies_*_00_24*.nc'))
rm_files = ['GEM_rockies_2013031906_00_24_surf.nc', 'GEM_rockies_2013031906_00_24_lvl.nc',
                        'GEM_rockies_2013041506_25_42.nc','GEM_rockies_2013061318_25_42.nc',
                        'GEM_rockies_2014021818_00_24.nc','GEM_rockies_2014102118_25_42.nc',
                        'GEM_rockies_2014102118_00_24.nc']
# all_files = set(glob.glob('GEM_rockies_*.nc'))# - set(glob.glob("*_lvl*")))
# all_files = [all_files - x for x in rm_files]
all_files = sorted(all_files)
# GEM_rockies_2013031906_00_24_surf.nc
#hgt_file = r'/media/data3/nicway/GEM/GDPS/GDPS_HGT/CMC_glb_HGT_SFC_0_latlon.24x.24_2017092700_P000_SUB.nc'
#ds_hgt_in = xr.open_dataset(hgt_file).isel(time=0).drop('time')

first_day = True # Flag to write header to csv files if first month

# Move to ascii dir
if not os.path.isdir(ascii_dir):
    os.mkdir(ascii_dir)

for cd in all_files:
    if cd in rm_files: # we don't want this file
        continue
    flag1 = False # flag to check we are not missing a forecast
    print cd

    # Load current file
    os.chdir(netcdf_dir)
    ds = xr.open_dataset(cd,engine='netcdf4')

    # Check if no HR (RH) variable is available
    if 'HR' not in ds:
        da_temp = ds.t.copy()
        da_temp.name = 'HR'
        ds['HR'] = da_temp.where(da_temp > 9999999) # Fill with missing (t always less than 999999)

    # Rename variables
    # Allow skip if variable is missing
    ds.rename(var_dic, inplace=True)



    # Apply a bias correction (optional)
    #ds['Qli'] = ds.Qli + 30
    #print "Warning, applying +30 ilwr bias correctoin"

    print 'Converting units to CHM units'
    ##### Convert units to CHM requirements

    # longitude
    ds['lon_0'] =  ds.lon_0 - 360

    # replace x,y (in distance (m)) to indices (wgrib does this for some reason!)
    ds['x']=np.arange(0,ds.x.size)
    ds['y']=np.arange(0,ds.y.size)

    # Apply a bias correction (optional)
    #ds['Qli'] = ds.Qli + 30
    #print "Warning, applying +30 ilwr bias correction"

    # Drop sigma dims
    ds = ds.isel(sigma=0).drop('sigma')
    # ds['t'] = ds.t.isel(sigma=0).drop('sigma')
    # ds['rh'] = ds.rh.isel(sigma=0).drop('sigma')
    # ds['GZ'] = ds.GZ.isel(sigma=0).drop('sigma')
    # ds['u'] = ds.u.isel(sigma=0).drop('sigma')
    # ds['vw_dir'] = ds.vw_dir.isel(sigma=0).drop('sigma')

    # Relative humidity
    ds['rh'] = ds.rh*100 # fraction to %

    # Pressure (after RH calcs)
    ds['press'] = ds['press'] # Appears to b in hPa already

    # Precipitation (liquid and solid) accumulated (m) to incremental (mm)
    ds['p'] = ds.PR.diff(dim='time', label='lower') * 1000
    # # Set values just below zero to zero
    # ds_p.values[ds_p.values<0] = 0
    # # First value is unknown (downside of saving as accum...) so we set it to -9999
    #  = xr.concat([ds.PR[0,:,:]*0-9999,ds_p],dim='time').transpose('time','y','x')

    # Select only times we want
    ds = ds.isel(time=np.arange(6,18))

    # Geopotential to height
    if 'GZ' in ds: # Some files are missing GZ (fine as long as its not the first one!)
        ds['HGT_surface'] = ds.GZ * 9.81

    # Rename time
    ds.rename({'time':'datetime'},inplace=True)


    ## Adjust to local time zone (i.e. from UTC to MST, local_time_offset should = -7)
    #ds['datetime'] = pd.to_datetime(ds.datetime.values) + datetime.timedelta(hours=local_time_offset)

    # Shift time stamp from END (GEM format)
    # to START (CHM format)
    ds['datetime'] = pd.to_datetime(ds.datetime.values) - datetime.timedelta(hours=output_dt)

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
