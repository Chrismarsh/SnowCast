# Merge all CHM output files into one netcdf file (easier to plot later)

# Assumes:
# 1) that output file name syntax is : XXX_out.txt where XXX is the three letter station/point code
# 2) Time zone is in UTC

# Saves to netcdf file in \points\ dir
import xarray as xr
import glob
import os
import sys
import imp
import pandas as pd
import datetime

#EXP_names = ['HRDPS_Historical','forecast_CRHO_spinup','GDPS_Current','HRDPS_Current_Snowpack']

# Unit conversion done
# Model p from mm to m
# swe from kg/m^2 to m

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file

if len(sys.argv) != 3:
    raise ValueError('Requires two arguments [configuration file] [chm_run_dir]')

# Get name of configuration file/module
configfile = sys.argv[1]
chm_run_dir = sys.argv[2]
print(chm_run_dir)

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
git_dir = X.git_dir

for c_exp in [chm_run_dir]:
    print(c_exp)
     # 1km
# #     main_dir   = os.path.normpath(r'C:\\Users\new356\Model_Output\CHM\Nov_2014')
#     main_dir = os.path.normpath(r'C:\Users\new356\Model_Output\CHM\SnowCast')

    mod_dir     = os.path.join(git_dir,'CHM_Configs',c_exp,'points')
    nc_file_out = 'CHM_pts.nc'
    # Move to Model dir
    os.chdir(mod_dir) 
    # Get files
    cfiles = glob.glob('*_out.txt')
    # Time zone
    UTC_to_MST = 0 # UTC 



    # Loop each station
    CHM_pts = []
    for cf in cfiles:
        cSta = cf.split('_')[0]
        print("processing " + cSta)

        # Import MODEL data to pandas dataframe
        modData = pd.read_csv(cf,sep=",",parse_dates=True) 
        modData.set_index('datetime',inplace=True)
        # Make datetime the index
        modData.index = pd.to_datetime(modData.index)
        modData.index = modData.index + datetime.timedelta(hours=UTC_to_MST)
        # Convert to data set and add station name
        c_ds = xr.Dataset(modData)
        c_ds['station'] = cSta
        c_ds.rename({'datetime':'time'}, inplace=True)
        # Save in list
        CHM_pts.append(c_ds)



    # concat all stations
    ds = xr.concat(CHM_pts,dim='station')
    
    # Convert unit of precipitaiotn from mm to m
    ds['p'] = ds.p / 1000
    ds['p_rain'] = ds.p_rain / 1000
    ds['p_snow'] = ds.p_snow / 1000

    # Convert unit of swe from kg/m^2 to m
    if 'swe' in ds.data_vars:
        ds['swe'] = ds.swe / 1000
    
    # Set -9999 (CHM missing value) to nan
    ds = ds.where(ds!=-9999)
    
    # Save out to netcdf
    ds.to_netcdf(nc_file_out,engine='netcdf4')
    
    print(ds)
