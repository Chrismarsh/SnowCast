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
os.environ['TZ'] = 'GMT'
time.tzset()

# Dirs
netcdf_dir = '/media/data3/nicway/GEM/GDPS/netcdf_archive'
os.chdir(netcdf_dir)

# Takes one argument, the date of missing forecast netcdf file (UTC)
date_m = sys.argv[-1] # i.e. 2017-01-09T01:00:00.000000000+0000

# Get date in datetime format
def get_date_fmt(date_m):
    for fmt in ('%Y-%m-%dT%H:00:00.000000000+0000','%Y-%m-%dT%H:00:00.000000000'):
        try:
            return datetime.datetime.strptime(date_m, fmt)
        except:
            pass
    raise ValueError('date formate not recognized')

new_d = get_date_fmt(date_m)        
#new_d = datetime.datetime.strptime(date_m, '%Y-%m-%dT%H:00:00.000000000+0000')
prv_d = new_d + datetime.timedelta(days=-1)
nxt_d = new_d + datetime.timedelta(days= 1)

# File names
file_for = 'GEM_GDPS_25km_%Y-%m-%dT%H:00:00.000000000.nc'
new_f = new_d.strftime(file_for)
prv_f = prv_d.strftime(file_for)
nxt_f = nxt_d.strftime(file_for)

# Open previous day
print("Opening previous file:",prv_f)
prv_ds = xr.open_dataset(prv_f,engine='netcdf4')
# Extract last 24 hours
new_ds = prv_ds.isel(datetime=np.arange(8,48)) # arange doesn't include the last number!!

# Open next day
#nxt_ds = xr.open_dataset(nxt_f,engine='netcdf4')
# Extract first 24 hours
#nxt_ds = nxt_ds.isel(datetime=np.arange(0,24)) # arange doesn't include the last number!!

# Concatonate data
#new_ds = xr.concat([prv_ds,nxt_ds],dim='datetime')

# Fill missing rad values in first hour (this is becase rad was saved as accumulated (dumb) and we don't have 0 hour)
# As a best guess, interpolate
# Set -9999 to nan
new_ds = new_ds.where(new_ds!=-9999)
# Qsi
df = new_ds['Qsi'].to_dataframe()
df_f = df.fillna(method='ffill')
#df_b = df.fillna(method='bfill')
#df3 = pd.concat((df_f, df_b))
#df3.groupby(df3.index).mean()
ds_Qsi = xr.Dataset.from_dataframe(df_f)
ds_Qsi.set_coords({'lat_0','lon_0'},inplace=True)
#ds_Qsi['Qsi'] = ds_Qsi.astype('float64')

# Qli
df = new_ds['Qli'].to_dataframe()
df_f = df.fillna(method='ffill')
df_f = df_f.convert_objects(convert_numeric=True)
#df_b = df.fillna('backfil')
#df3 = pd.concat((df_f, df_b))
#df3.groupby(df3.index).mean()
ds_Qli = xr.Dataset.from_dataframe(df_f)
ds_Qli.set_coords({'lat_0','lon_0'},inplace=True)
# Check no missing values in output file
#print ds_2.isnull().sum().values

# Merge back in
new_ds = new_ds.drop(['Qsi','Qli']) #,'gridlat_0','gridlon_0'])
ds_out =  xr.merge([ds_Qsi,new_ds])
ds_out =  xr.merge([ds_Qli,ds_out])
ds_out.set_coords({'lat_0','lon_0'},inplace=True)
# fix dim on gridlat_0...
ds_out['lat_0'] = prv_ds.lat_0
ds_out['lon_0'] = prv_ds.lon_0

# Set nan to -9999
ds_out = ds_out.fillna(-9999)
print ds_out
#print ds_out['Qsi'].isel(datetime=23)
# Save new netcdf file (if it doesn't exist)
if os.path.isfile(new_f):
	print 'File exists! NOT replacing it. Delete it if you want to overwrite.'
	print new_f
else:
	print 'File does not exist, adding new merged netcdf file'
	ds_out.to_netcdf(new_f,engine='netcdf4')




