import imp
import numpy as np
import os
import sys
import xarray as xr

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) == 1:
    raise ValueError('Requires one argument [configuration file]')

# Get name of configuration file/module
configfile = sys.argv[-1]

# Load in configuration file as module
X = imp.load_source('', configfile)

# Assign to local variables
data_dir = X.data_dir

AB_recent = os.path.join(data_dir, 'AB_recent', 'netcdf','AB_NRT.nc')
AB_POR = os.path.join(data_dir, 'AB_POR', 'netcdf', 'AB_SWE_SD_NRT.nc')
BC_CWY = os.path.join(data_dir, 'BC_NRT', 'netcdf', 'BC_NRT.nc') # Current Water Year (CWR)
BC_HIST = os.path.join(data_dir, 'BC_HIST', 'netcdf', 'BC_HIST.nc')
ABE_AGG_HIST = os.path.join(data_dir, 'ABE_AGG_HIST', 'netcdf', 'ABE_AGG_HIST.nc') # MST
CRHO = os.path.join(data_dir, 'CRHO_HIST', 'netcdf', 'CRHO_1hour.nc') # MST
CRHO_NRT = os.path.join(data_dir, 'CRHO_NRT', 'netcdf', 'CRHO_NRT.nc') # MST

CRHO_time_zone = 7 # (HIST AND NRT) MST to UTC
ABE_AGG_HIST_time_zone = 7 # MST to UTC

merged_dir = os.path.join(data_dir,'merged')
# Make if does not exist
if not os.path.exists(merged_dir):
    os.makedirs(merged_dir)
netcdf_file_out = os.path.join(merged_dir, 'Hourly_Merged.nc')

# Merge Networks
ds_AB_recent = xr.open_dataset(AB_recent)
ds_AB_POR = xr.open_dataset(AB_POR)
ds_BC_CWR = xr.open_dataset(BC_CWY)
ds_BC_HIST = xr.open_dataset(BC_HIST)
ds_CRHO = xr.open_dataset(CRHO)
ds_CRHO_NRT = xr.open_dataset(CRHO_NRT)
ds_ABE_AGG = xr.open_dataset(ABE_AGG_HIST)

# Make all datasets same time zone and variable names
# All to MST
ds_CRHO['time_hrly'] = ds_CRHO['time_hrly'] + np.timedelta64(CRHO_time_zone,'h')
ds_CRHO.rename({'station':'staID','time_hrly':'Time_UTC'}, inplace=True);

ds_CRHO_NRT['Time_MST'] = ds_CRHO_NRT['Time_MST'] + np.timedelta64(CRHO_time_zone,'h')
ds_CRHO_NRT.rename({'station':'staID','Time_MST':'Time_UTC'}, inplace=True);

ds_ABE_AGG['Time_MST'] = ds_ABE_AGG['Time_MST'] + np.timedelta64(ABE_AGG_HIST_time_zone,'h')
ds_ABE_AGG.rename({'Time_MST':'Time_UTC'}, inplace=True);

# Drop CRHO variables we are not interested in (still in orig file if we want them)
ds_CRHO = ds_CRHO[['WindDirectionatA',
 'TotalPressureUnadjustedA',
 'DownwardSolarRadiation',
 'ScalarWindSpeedA',
 'SnowDepthA',
 'AirtemperatureA',
 'IncrementalPrecipitationA',
 'IncrementalPrecipitationC',
 'UpwardSolarRadiation',
 'AirMoistureContentA',
 'UpwardTerrestrialRad',
 'DownwardTerrestrialRad',
 'SnowWaterEquivelentA']]

orig_coords = ['Lat','Lon','Elevation','network','station_name'] # combine_first() can't handel coords merging

ds_AB_recent.reset_coords(orig_coords, inplace=True);
ds_AB_POR.reset_coords(orig_coords, inplace=True);
ds_BC_CWR.reset_coords(orig_coords, inplace=True);
ds_BC_HIST.reset_coords(orig_coords, inplace=True);
ds_CRHO.reset_coords(orig_coords, inplace=True);
ds_CRHO_NRT.reset_coords(orig_coords, inplace=True);
ds_ABE_AGG.reset_coords(orig_coords, inplace=True);

# Merge AB data together (hist to midnight, and last few days)
###### This step drops coords info so leaving out most recent data for now
ds_AB_mrg = ds_AB_POR.combine_first(ds_AB_recent)

# Merge BC stations
ds_BC_merg = xr.merge([ds_BC_HIST, ds_BC_CWR])
ds_BC_HIST = None
ds_BC_CWR = None

# Merge AB and BC pillows
ds_BC_AB = xr.merge([ds_AB_mrg,ds_BC_merg])
ds_AB_mrg = None
ds_BC_merg = None

# Rename BC AB naming to match CRHO name format
var_dict = {'AirTemperature':'AirtemperatureA','Precipitation':'CummulativePrecipitationA',
            'SWE':'SnowWaterEquivelentA','Snowdepth':'SnowDepthA'}

ds_BC_AB.rename(var_dict, inplace=True);

# Adjust units to be metric standard
ds_BC_AB['SnowWaterEquivelentA'] = ds_BC_AB.SnowWaterEquivelentA / 1000.0 # mm to m
ds_BC_AB['CummulativePrecipitationA'] = ds_BC_AB.CummulativePrecipitationA / 1000.0 # mm to m
ds_BC_AB['SnowDepthA'] = ds_BC_AB.SnowDepthA / 100.0 # cm to m

# Merge CRHO HIST and CRHO NRT (HIST has been more rigoursly QC'ed to use it first)
# First merge different type of precip gauges in CRHO historical data
# IncrementalPrecipitationA --> Pluvio gauges
# IncrementalPrecipitationB --> Tipping bucket (bad in winter months)
# IncrementalPrecipitationC --> Genor
# Here we merge IncrementalPrecipitationC into IncrementalPrecipitationA.
ds_CRHO['IncrementalPrecipitationA'] = ds_CRHO.IncrementalPrecipitationA.combine_first(ds_CRHO.IncrementalPrecipitationC)
# Then update with NRT data
ds_CRHO_all = ds_CRHO.combine_first(ds_CRHO_NRT)

# Merge CRHO with other AB and BC data
ds_merged = xr.merge([ds_CRHO_all,ds_BC_AB])
ds_CRHO = None
ds_CRHO_NRT = None
ds_BC_AB = None

# Rename ds_ABE_AGG naming to match CRHO name format
var_dict = {'RealtiveHumidity':'AirMoistureContentA','WindSpeed':'ScalarWindSpeedA','WindDirection':'WindDirectionatA',
            'AirTemperature':'AirtemperatureA','Precipitation':'IncrementalPrecipitationA',}
ds_ABE_AGG.rename(var_dict, inplace=True);

# Adjust units to be metric standard
ds_ABE_AGG['IncrementalPrecipitationA'] = ds_ABE_AGG.IncrementalPrecipitationA / 1000.0 # mm to m

def find_common_staID(ds1,ds2):
    same = list(set(list(ds1.staID.values)).intersection(list(ds2.staID.values)))
    return(ds1.sel(staID=same).station_name)
    # Usage find_common_staID(ds_ABE_AGG,ds_merged)

# Merge ds_merged with ds_ABE_AGG 
# Use combine_first because there are duplicate stations (met vars and snow vars)
# ds_merged_2 = xr.merge([ds_merged, ds_ABE_AGG])
ds_merged_2 = ds_ABE_AGG.combine_first(ds_merged)
ds_merged = None
ds_ABE_AGG = None

# Set coords
ds_merged_2.set_coords(orig_coords, inplace=True);

# Save as netcdf file
ds_merged_2.to_netcdf(netcdf_file_out)
print(netcdf_file_out)


