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
import distutils
from distutils import dir_util
start_time = time.time()
# Hack to force datetimes to display in GMT/UTC (numpy 1.11.1 has fixed this but other dependent modules (pynio) can't handel numpy 1.11.1)
os.environ['TZ'] = 'GMT'
time.tzset()

# Load in config file
#######  load user configurable paramters here    #######

# Get name of configuration file/module
configfile = sys.argv[-1]

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assinge to local variables
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
all_files =  glob.glob('*.nc')

# Sort file names (open_mfdataset _should_ handle this, but this is a hack to put in correct order)
all_files = sorted(all_files)

# Open most recent forecast
ds = xr.open_dataset(all_files[-1],engine='netcdf4')

# Trim to forecast hours we want
ds = ds.isel(datetime=np.arange(6,48))

# Adjust to local time zone (if requested) 
ds['datetime'] = pd.to_datetime(ds.datetime.values) + datetime.timedelta(hours=local_time_offset)

# Trim to lat long box
ds = ds.where((ds.gridlat_0>lat_r[0]) & (ds.gridlat_0<lat_r[1]) & (ds.gridlon_0>lon_r[0]) & (ds.gridlon_0<lon_r[1]), drop=True)

# Move to ascii dir
if not os.path.isdir(ascii_dir):
    os.mkdir(ascii_dir)
os.chdir(ascii_dir)

# Make backup copy of ascii files
distutils.dir_util.copy_tree(ascii_dir,ascii_dir+'_backup')

# Load in json file
with open(Forcing_config_file) as json_data:
    config = json.load(json_data)

# Loop through forcing files
for pt in config:
    print pt
    # Load in forcing file
    i = int(pt.split('_')[1])
    j = int(pt.split('_')[2])
    modData = pd.read_csv(config[pt]["file"], sep="\t", parse_dates=True)
    modData.set_index('datetime', inplace=True)
    modData.index = pd.to_datetime(modData.index)
    # print "current last time step is:"
    # print modData.index[-1]

    # Select point
    sub_ds = ds.isel(xgrid_0=i, ygrid_0=j)
    # Convert to dataframe
    df = sub_ds.to_dataframe()
    # Drop unwanted vars/coords
    #df.drop(['HGT_P0_L1_GST0', 'xgrid_0', 'ygrid_0', 'gridlat_0', 'gridlon_0'], axis=1, inplace=True)
    df.drop(['HGT_P0_L1_GST0', 'gridlat_0', 'gridlon_0'], axis=1, inplace=True)
    # print "loaded netcdf file date range is:"
    # print df.index[0]
    # print df.index[-1]

    # Merge dataframes (let most recent forecast overwrite previous dates)
    merged = df.combine_first(modData)
    #merged = modData.merge(df,how='inner')
    # print "new df date range is "
    # print merged.index[0]
    # print merged.index[-1]

    # Overwrite ascii file
    of = open('point_' + str(i) + '_' + str(j) + '.chm', 'w')
    merged.to_csv(of, sep='\t', date_format='%Y%m%dT%H%M%S')
    of.close()
    merged = None


print("--- %s minutes ---" % ((time.time() - start_time)/60))


print 'finished!'
