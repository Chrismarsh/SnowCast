# Convert ascii files (one var, one time step) to netcdf files

import datetime
import glob
import imp
import json
import numpy as np
import os
import pandas as pd
import sys
import threading
import time
import xarray as xr
from itertools import compress

# Hack to force datetimes to display in GMT/UTC (numpy 1.11.1 has fixed this but other dependent modules (pynio) can't handel numpy 1.11.1)
os.environ['TZ'] = 'GMT'
time.tzset()

# USER INPUT (change to config file later)
# 1km
#ascii_dir='/media/data3/nicway/GEM/Nov2014/1km/ascii'
#netcdf_dir='/media/data3/nicway/GEM/Nov2014/1km/netcdf'
#elev_file='/media/data3/nicway/GEM/Nov2014/1km/constant/2014120212_023_MX.csv'
# 250m
ascii_dir='/media/data3/nicway/GEM/Nov2014/250m/ascii'
netcdf_dir='/media/data3/nicway/GEM/Nov2014/250m/netcdf'
elev_file='/media/data3/nicway/GEM/Nov2014/250m/constant/2014112712_000_MX.csv'
#


# Incremental variables
varlist=['DN','HR_2m','HU_2m','I4','I5','I6','P0_SF','SD','TT_2m','UU_10m','VV_10m','WGE','WGN','WGX']
fullname=['Snow Density','Relative Humidity at 2m','Specific Humidity at 2m','Water in the snow pack','Snow water equivalent','Albedo of Snow','Surface Pressure','Snow Depth','Air Temperature 2m above surface','U component','V component','Wind Gust Estimate','Wind gust minimum','Wind gust maximum']
units=['kg/m3','Fraction','kg/kg','kg/m2','kg/m2','fraction','mb','cm','C','kts','kts','m/s','m/s','m/s']
# Make dictionaries for quick lookup
fullname_dic = dict(zip(varlist,fullname))
unit_dic     = dict(zip(varlist,units))

# Accumulated variables (that require previous time step, thus separate processing)
varlist_accum=['PR','RN','SN']
fullname_accum=['Total Precipitation','Rainfall','Snowfall']
units_accum=['m','m','m']
# Make dictionaries for quick lookup
fullname_dic_accum = dict(zip(varlist_accum,fullname_accum))
unit_dic_accum     = dict(zip(varlist_accum,units_accum))

# CHM names
chm_dic = {'PR':'p','RN':'p_rain','SN':'p_snow','HR_2m':'rh','I5':'swe','I6':'snowalbedo','P0_SF':'press','SD':'snowdepthavg','TT_2m':'t'}


# Move to input
os.chdir(ascii_dir)

# Common structurs
L = np.arange(0,1024)

# Loop for each variable
incr_ds = xr.Dataset()
for cvar in varlist:
	print fullname_dic[cvar]
	# Get all file names for current var
	#print 'Looking for... *_'+str(cy)+'_'+str(cm)+'_*'
        cfiles = glob.glob('*'+cvar+'*')

        # Sort file names (open_mfdataset _should_ handle this, but this is a hack to put in correct order)
        cfiles = sorted(cfiles)

	# Select forecast hours we want (12-23)
 	#2014120112_014_VV_10m.csv
	fHour = [np.int(x.split('_')[1][-2:])>=13 for x in cfiles]
	selFiles = list(compress(cfiles,fHour))
	
	# For each time step
	list_ds = []
	list_time = []
	for cts in selFiles:
		# Import file
		df = pd.read_csv(cts)
	 	df.drop(['Unnamed: 3'],axis=1, inplace=True) # Remove blank from extra comma
		df.rename(columns={'lat': 'latitude', 'lng': 'longitude', 'val':cvar}, inplace=True)
		# Reshape (not sure if this works correctly, has missing nan inside matrix)
		#df_2 = df.pivot(index='lat', columns='lng', values='val')

		#df = ds.latitude.to_dataframe()['latitude']
		#df df.values.reshape(1024,1024)
	
		# Reshape data into a grid
		df_grid = df[cvar].values.reshape(1024,1024)
		# Reshape lat and long
		df_lat = df['latitude'].values.reshape(1024,1024)		
		df_lon = df['longitude'].values.reshape(1024,1024)

		# Create dataset
		#ds = xr.Dataset.from_dataframe(df) 
	
		# Get time step
		str1 = cts.split('_')[0]
		str2 = cts.split('_')[1]
		yyyy = str1[0:4]
		mm   = str1[4:6]
		dd   = str1[6:8]
		fi   = str1[8:10]
		fH   = str2[1:3]
		#list_time.append(datetime.datetime(int(yyyy),int(mm),int(dd),int(fi))+ datetime.timedelta(hours=int(fH)))	
		ctime = datetime.datetime(int(yyyy),int(mm),int(dd),int(fi))+ datetime.timedelta(hours=int(fH))

		# Create dataArray
                da = xr.DataArray(df_grid,dims=['x','y'],coords={'time':ctime,'x':L,'y':L,'latitude':(('x','y'),df_lat),'longitude':(('x','y'),df_lon)})
		
		# Store dataset
		list_ds.append(da.to_dataset(name=cvar))

	# Merge all time steps together
	ds_t = xr.concat(list_ds,dim='time')
	#ds_t['time'] = pd.DatetimeIndex(list_time)
	
	# Add variable metadata
	ds_t.get(cvar).attrs['unit'] = unit_dic[cvar]
	ds_t.get(cvar).attrs['long_name'] = fullname_dic[cvar]

	# Merge with dataset containing all variables
	incr_ds = xr.merge([incr_ds,ds_t])
	ds_t=None

## Process accumulation variables (we need overlapped times due to the way GEM was run (forecast mode))
# Loop for each variable
accum_ds = xr.Dataset()
for cvar in varlist_accum:
        print fullname_dic_accum[cvar]
        # Get all file names for current var
        #print 'Looking for... *_'+str(cy)+'_'+str(cm)+'_*'
        cfiles = glob.glob('*'+cvar+'*')

	# Sort file names (open_mfdataset _should_ handle this, but this is a hack to put in correct order)
        cfiles = sorted(cfiles)

        # Sort file names (open_mfdataset _should_ handle this, but this is a hack to put in correct order)
        # Select forecast hours we want (11-23) 
        #2014120112_014_VV_10m.csv
        fHour = [np.int(x.split('_')[1][-2:])>=12 for x in cfiles]
        selFiles = list(compress(cfiles,fHour))
	
        # For each time step
        list_ds = []
        list_time = []
        for cts in selFiles:
                # Import file
                df = pd.read_csv(cts)
                df.drop(['Unnamed: 3'],axis=1, inplace=True) # Remove blank from extra comma
                df.rename(columns={'lat': 'latitude', 'lng': 'longitude', 'val':cvar}, inplace=True)

		# Reshape data into a grid
                df_grid = df[cvar].values.reshape(1024,1024)
                # Reshape lat and long
                df_lat = df['latitude'].values.reshape(1024,1024)
                df_lon = df['longitude'].values.reshape(1024,1024)

                # Create dataset
                #ds = xr.Dataset.from_dataframe(df)

                # Get time step
                str1 = cts.split('_')[0]
                str2 = cts.split('_')[1]
                yyyy = str1[0:4]
                mm   = str1[4:6]
                dd   = str1[6:8]
                fi   = str1[8:10]
                fH   = str2[1:3]
                #list_time.append(datetime.datetime(int(yyyy),int(mm),int(dd),int(fi))+ datetime.timedelta(hours=int(fH)))
		ctime = datetime.datetime(int(yyyy),int(mm),int(dd),int(fi))+ datetime.timedelta(hours=int(fH))

		# Create dataArray
                da = xr.DataArray(df_grid,dims=['x','y'],coords={'time':ctime,'x':L,'y':L,'latitude':(('x','y'),df_lat),'longitude':(('x','y'),df_lon)})

                # Store dataset
                list_ds.append(da.to_dataset(name=cvar))
		da=None

        # Merge all time steps together
        ds_t = xr.concat(list_ds,dim='time')
        #ds_t['time'] = pd.DatetimeIndex(list_time)
	
	# Take difference (time stamp at end of difference)
	ds_t_diff = ds_t.diff(dim='time',n=1,label='upper')
	
	# Select indices to remove (extra initial hour every 12 hours). Returns boolean.
	I_good = ds_t_diff.time.diff(dim='time',n=1,label='upper')!=np.timedelta64(0,'ns')
	# Missing last time step due to diff above, so fill it in manualy
	I_good = xr.concat([xr.DataArray([True],[('time',[ds_t.time.values[-1]])]),I_good],dim='time')
 		
	# Select only those times we want
	ds_new = ds_t_diff.get(cvar)[I_good].to_dataset()
	
	# Add lat/long back in
	#ds_new['latitude'] = ds_t.latitude.isel(time=0).reset_coords(names='time',drop=True)
	#ds_new['longitude'] = ds_t.longitude.isel(time=0).reset_coords(names='time',drop=True)
	#ds_new.set_coords(['latitude','longitude'],inplace=True)
        
	# Add variable metadata
        ds_new.get(cvar).attrs['unit'] = unit_dic_accum[cvar]
        ds_new.get(cvar).attrs['long_name'] = fullname_dic_accum[cvar]

        # Merge with dataset containing all variables
	accum_ds = xr.merge([accum_ds,ds_new])
        
	# Clean up vars to be safe
	ds_t=None
	ds_t_diff=None
	ds_new=None
	I_good=None
	
# Merge
ds_temp = xr.merge([accum_ds,incr_ds])
accum_ds=None
incr_ds=None
print ds_temp

# Add Elevation
df_e = pd.read_csv(elev_file)
df_e.drop(['Unnamed: 3'],axis=1, inplace=True) # Remove blank from extra comma
df_e.rename(columns={'lat': 'latitude', 'lng': 'longitude', 'val':'elevation'}, inplace=True)
# Reshape data into a grid
df_grid = df_e['elevation'].values.reshape(1024,1024)
# Reshape lat and long
df_lat = df_e['latitude'].values.reshape(1024,1024)
df_lon = df_e['longitude'].values.reshape(1024,1024)
# Create dataset
ds_elev = xr.DataArray(df_grid,dims=['x','y'],coords={'x':L,'y':L,'latitude':(('x','y'),df_lat),'longitude':(('x','y'),df_lon)}).to_dataset(name='elevation')
ds_elev['elevation'] = ds_elev.elevation/9.807 # Convert from m2 s-2 to gpm
print ds_elev
ds_merged = xr.merge([ds_temp,ds_elev]) # Merge
print ds_merged

# Fix lat
ds_merged['longitude'] = ds_merged.longitude - 360

# CHM var names
ds_merged.rename(chm_dic,inplace=True)

# CHM units
# RH fraction to %
ds_merged['rh'] = ds_merged.rh*100
ds_merged['rh'].attrs['unit'] = '%'

# press mb to ?

# SWE kg/m2 to m
ds_merged['swe'] = ds_merged.swe/1000
ds_merged['swe'].attrs['unit'] = 'm'

# SD cm to m
ds_merged['snowdepthavg'] = ds_merged.snowdepthavg/100
ds_merged['snowdepthavg'].attrs['unit'] = 'm'

# precip vars m to mm
ds_merged['p'] = ds_merged.p*1000
ds_merged['p_rain'] = ds_merged.p_rain*1000
ds_merged['p_snow'] = ds_merged.p_snow*1000
ds_merged['p'].attrs['unit'] = 'mm'
ds_merged['p_rain'].attrs['unit'] = 'mm'
ds_merged['p_snow'].attrs['unit'] = 'mm'

# Winds (TODO: add rotation)
# Calc mag and kts to m/s
ds_merged['u'] = np.sqrt(ds_merged.UU_10m**2 + ds_merged.VV_10m**2) * 0.514444
ds_merged['u'].attrs['unit'] = 'm/s'
# Calc dir
ds_merged['vw_dir'] = np.arctan2(-1*ds_merged.UU_10m,-1*ds_merged.VV_10m) * (180/np.pi) + 180
ds_merged['vw_dir'].attrs['unit'] = 'Degrees from north (clockwise)'

# Set coords
ds_merged.set_coords(['latitude','longitude','elevation'],inplace=True)

# Change time
ds_merged.rename({'time':'datetime'},inplace=True)

# Save as netcdf file
print ds_merged
os.chdir(netcdf_dir)
nc_file_out = 'GEM_250m_Nov_2014_Storm.nc'
print('Writing netcdf file')
ds_merged.to_netcdf(nc_file_out,engine='netcdf4')

