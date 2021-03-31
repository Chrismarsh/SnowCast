import xarray as xr
import os
import imp
import send_mail
import sys
import numpy as np
import pandas as pd
import datetime
import json
import time
import threading
# Hack to force datetimes to display in GMT/UTC (numpy 1.11.1 has fixed this but other dependent modules (pynio) can't handel numpy 1.11.1)
os.environ['TZ'] = 'GMT'
time.tzset()

start_time = time.time()

def SPHM_2_RELHM(SPHM,PRESS,TAIR):
    import numpy as np
    # ! public function SPHM2RELHM: compute relative humidity from specific humidity
    # ! ***************************************************************************************************************
    # ! ---- This is done with respect to water ONLY ----
    # !
    # ! All units are SI standard - i.e. Kelvin and pascals
    # ! Based on Tetens' formula (1930)
    # ! ***************************************************************************************************************
    # FUNCTION SPHM2RELHM(SPHM, PRESS, TAIR)
    # IMPLICIT NONE

    # REAL(DP), INTENT(IN)         :: SPHM      ! Specific Humidity (g/g)
    # REAL(DP), INTENT(IN)         :: PRESS     ! Pressure              (Pa)
    # REAL(DP), INTENT(IN)         :: TAIR      ! Air temp (K)

    # REAL(DP)                     :: VPSAT     ! vapour pressure at T  (Pa)
    # REAL(DP)                     :: TDCEL     ! Dewpt in celcius      (C)
    # !REAL(DP)                     :: DUM       ! Intermediate

    # ! Units note :              Pa = N m-2 = kg m-1 s-2
    SATVPFRZ=     610.8       # Saturation water vapour pressure at 273.16K (Pa)
    TFREEZE = 273.15
    W_RATIO =       0.622     # molecular weight ratio of water to dry air (-)

    TDCEL = TAIR-TFREEZE
    VPSAT = SATVPFRZ * np.exp( (17.27*TDCEL) / (237.30 + TDCEL) )       #! Vapour Press      (Pa)
    SPHM2RELHM = (SPHM * PRESS)/(VPSAT * (W_RATIO + SPHM*(1.-W_RATIO))) * 100.0
    # Bounds
    SPHM2RELHM = SPHM2RELHM.where(SPHM2RELHM <= 100).fillna(100)
    SPHM2RELHM = SPHM2RELHM.where(SPHM2RELHM >= 5).fillna(5)

    return SPHM2RELHM

def add_datetime_dataset(ds_in):
	import re
        # Replace dummey time variable with datetime64
        # TODO: Remove hardcoded variable name
        init_time = ds_in.TMP_P0_L103_GLL0.attrs['initial_time']
        DT = re.split(' ',init_time)
        D = re.split('/',DT[0])
        HHMM = re.split(':',DT[1].replace("(","").replace(")",""))
        T_init = datetime.datetime(int(D[2]),int(D[0]),int(D[1]),int(HHMM[0])+3,int(HHMM[1])) # +3 is because we start on forecast hour 3 (disregard hour 00 as it is just initial conditions... and no precip values)
        TimeS = pd.date_range(T_init, periods=len(ds_in.forecast_hour),freq='3H')
        ds_in['forecast_hour'] = TimeS
	ds_in.rename({'forecast_hour':'time'},inplace=True)
        return ds_in

def add_datetime_dataarray(dr_in):
        import re
        # Replace dummey time variable with datetime64
        init_time = dr_in.initial_time
        DT = re.split(' ',init_time)
        D = re.split('/',DT[0])
        HHMM = re.split(':',DT[1].replace("(","").replace(")",""))
        T_init = datetime.datetime(int(D[2]),int(D[0]),int(D[1]),int(HHMM[0])+3,int(HHMM[1])) # +3 is because we start on forecast hour 3 (disregard hour 00 as it is just initial conditions... and no precip values)
        TimeS = pd.date_range(T_init, periods=len(dr_in.forecast_hour),freq='3H')
        dr_in['forecast_hour'] = TimeS
	dr_in = dr_in.rename({'forecast_hour':'time'})
        return dr_in

# Create preprocessing function to handle loading and time
def preprocess(x):
    x.load()
    #x = x.drop('gridrot_0')
    [cvar for cvar in x.data_vars]
    x = xr.concat([x], dim='forecast_hour')
    # units can be in hour or minuts (I have no idea why)
    if x[cvar].forecast_time_units=='hours':
    	x['forecast_hour'] = x[cvar].attrs['forecast_time']
    elif x[cvar].forecast_time_units=='minutes':
   	x['forecast_hour'] = x[cvar].attrs['forecast_time']/60.0 # minutes to hours
    else:
	import sys
	print('found forecast_time_units not expected')
	sys.exit()
    return x

def load_GEM_4d_var(PresLevs,UA_files,var_name,var_name_new,preprocess):
	import xarray as xr
        ds_UA = xr.Dataset()
        for cP in PresLevs:
                # Get all time step files for this pressure level
                cfiles = [x for x in UA_files if '_'+cP in x] # Underscore needed to exclude patterns in date
                #print(cfiles)
                # Load and conact by time
                #ds_t = xr.open_mfdataset(cfiles,concat_dim='time',engine='pynio',lock=threading.Lock())
                ds_t = xr.open_mfdataset(cfiles,concat_dim='forecast_hour',engine='pynio',preprocess=lambda x: preprocess(x))
		# Rename var based on file name pressure level
                ds_t.rename({var_name:var_name_new+cP},inplace=True)
                # Combine
                ds_UA = xr.merge([ds_UA,ds_t])
        # Drop unneed vars
        # ds_UA = ds_UA.drop('gridrot_0')
        # Conact by pressure level
        ds_com = xr.concat([ds_UA[cvar] for cvar in ds_UA.data_vars],dim='PressLev')
        # Rename
	ds_com.name = var_name_new
	# return
        return ds_com

# Start Main

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) == 1:
    raise ValueError('GRIB2_GDPS_to_NETCDF.py requires one argument [configuration file] (i.e. python GRIB2_to_CHM_forcing.py forcing_config.py')


# Get name of configuration file/module
configfile = sys.argv[-1]

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assinge to local variables
download_dir = X.download_dir
netcdf_dir   = X.netcdf_dir
var_dic = X.var_dic
domain =X.domain
# Move to input
os.chdir(download_dir)

# Get all file names
# TODO: Only list .grib2 files!!!!
all_files = os.listdir(download_dir)

# import and combine all grib2 files
print 'Opening all grib2 data files'

# Option, create different file list for surface and upper air files. Load in separatly. 
UA_TMP = [x for x in all_files if 'TMP_ISBL' in x]
UA_HGT = [x for x in all_files if 'HGT_ISBL' in x]

# Presure levels to extract air temperature from
PresLevs = ['1015','1000','985','970','950','925','900']

srf_files = [x for x in all_files if not 'HGT_ISBL' in x and not 'TMP_ISBL' in x]

# Load surface variables
print('Loading Surface variables')
# ds = xr.open_mfdataset(srf_files,concat_dim='time',engine='pynio',lock=threading.Lock())
try:
    ds = xr.open_mfdataset(srf_files,concat_dim='forecast_hour',engine='pynio',preprocess=lambda x: preprocess(x))
    ds = add_datetime_dataset(ds)
except:
    send_mail.send(str('GDPS GRIB to NETCDF: Cannot open GDPS surface grib2 files'))

# Load upper atmosphere variables
print('Loading upper air Temperature')
ds_UA_T   = load_GEM_4d_var(PresLevs,UA_TMP,'TMP_P0_L100_GLL0','TMP_',preprocess)
ds_UA_T   = add_datetime_dataarray(ds_UA_T)

print('Loading upper air height at pressurelevels')
ds_UA_HGT = load_GEM_4d_var(PresLevs,UA_HGT,'HGT_P0_L100_GLL0','HGT_',preprocess)
# Convert Geopotential height to geometric height (http://www.pdas.com/geopot.pdf)
#ds_UA_HGT = ds_UA_HGT* 6371*1000 / (6371*1000/()-ds_UA_HGT)
ds_UA_HGT = add_datetime_dataarray(ds_UA_HGT)

# Merge together
ds_UA = xr.merge([ds_UA_T,ds_UA_HGT])

# Approx method of calculating lapse rate (diff from lower and upper atmos temp)
ds_LR = -1*(ds_UA.TMP_[6,:,:,:] - ds_UA.TMP_[0,:,:,:]) / (ds_UA.HGT_[6,:,:,:] - ds_UA.HGT_[0,:,:,:])
ds_LR.name = 't_lapse_rate'

# More accurate but far too slow method of calc lapse rate
#print("Calculating lower-atmosphere lapse rate")
#ds_LR = ds.TMP_P0_L103_GST0 * 0 - 9999 # Quick way to make dataarray with -9999 values but with correct dims/coords
#for cts in np.arange(0,len(ds_UA.time)):
#        print(cts)
#	for cx in ds_UA.xgrid_0.values:
#		for cy in ds_UA.ygrid_0.values:
#			x_temp = ds_UA.TMP_[:,cts,cy,cx] # Grab the vertical profile of air temperature
#			y_hgt  = ds_UA.HGT_[:,cts,cy,cx] # Grab the vertical heights of air temperature values
#			s      = np.polyfit(y_hgt,x_temp,1) # Fit a line to the data
#			ds_LR[cts,cy,cx].values = s[0] # Grab the slope (first element)

ds = xr.merge([ds,ds_LR])

# Get time step (in seconds)
dt_s = 3*60*60 # seconds (hard coded for now)

print 'Renaming variables to CHM syntax'
# Change names
ds.rename(var_dic,inplace=True)

print 'Converting units to CHM units'
##### Convert units to CHM requirements
# TODO: account for below freezing
ds['rh'] = SPHM_2_RELHM(ds.SPFH_P0_L1_GLL0,ds.press,ds.t) # g/g, pa, K --> RH %
print(ds.rh.min().values)
print(ds.rh.max().values)
# Air temperature
ds['t'] = ds.t - 273.15

# Precipitation rate to accumulation (mm)
ds['p'] = ds['p'] * dt_s # density of water cancels out m to mm conversion

# Pressure
ds['press'] = ds['press'] / 100 # Pa to hPa

##### Radiation
# Shortwave radiation incoming
Qsi_wm2 = ds.Qsi.diff(dim='datetime')/dt_s # j/m2 to j/(s*m2)
# Set SW values just below zero to zero
Qsi_wm2.values[Qsi_wm2.values<0] = 0
# First value is unknown (downside of saving as accum...) so we set it to -9999
ds['Qsi'] = xr.concat([ds.Qsi[0,:,:]*0-9999,Qsi_wm2],dim='datetime').transpose('datetime','lat_0', 'lon_0')

# Longwave radiation incoming
Qli_wm2 = ds.Qli.diff(dim='datetime')/dt_s # j/m2 to j/(s*m2)
# First value is unknown (downside of saving as accum...) so we set it to -9999
ds['Qli'] = xr.concat([ds.Qli[0,:,:]*0-9999,Qli_wm2],dim='datetime').transpose('datetime','lat_0', 'lon_0')

# Adjust lon to be centered at 0
ds['lon_0'] = ds.lon_0 - 360

# Move to netcdf dir
if not os.path.isdir(netcdf_dir):
    os.mkdir(netcdf_dir)
os.chdir(netcdf_dir)

# Export to netcdf
nc_file_out = 'GEM_GDPS_'+domain+'_'+str(ds.datetime[0].values)+'.nc'
print('Writing netcdf file')
try:
    ds.to_netcdf(nc_file_out,engine='netcdf4')
except:
    send_mail.send(str('GDPS GRIB to NETCDF: Error writing to netcdf file.'))

