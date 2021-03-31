import numpy as np
import xarray as xr
import sys
import os
import imp
import matplotlib
import matplotlib.pyplot as plt

#TODO: Add constant check for some variables

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) == 1:
    sys.exit('Requires one argument [configuration file]')

# Get name of configuration file/module
configfile = sys.argv[-1]

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
data_dir = X.data_dir

hourly_merged = os.path.join(data_dir,'merged','Hourly_Merged.nc')

QC_dir = os.path.join(data_dir,'QC')
# Make if does not exist
if not os.path.exists(QC_dir):
    os.makedirs(QC_dir)
netcdf_file_out = os.path.join(QC_dir, 'Hourly_QC.nc')

# QC merged data
ds = xr.open_dataset(hourly_merged) #, chunks={'Time_UTC':1, 'staID':10})

# Quality control data here
def QC_min_max(da, vmin, vmax):
    return da.where((da <= vmax) &  (da >= vmin))

def QC_ROC(da, ROC_thress, ROC_window):
    return da.groupby('staID').apply(lambda x: remove_outliers_via_filter(x,ROC_thress,ROC_window))

def remove_outliers_via_filter(x,threshold,window):
    if ((sum(np.isnan(x.values))/len(x.values)>0.9) | np.isnan(threshold)): # Mostly nan, just return x, otherwise filter fails
        # Threshold of np.NaN indicates this method is not suitable for this type of variable (i.e. incremntal precipitation)
        #print('Less than 10% data for ',str(x.staID),str(x.name))
        return x
    else: # Have some data, apply the median filter and remove differences greater than threshold
        # Apply median filter
        temp = x.to_series().rolling(window=window, center=True).median().fillna(method='bfill').fillna(method='ffill')
        # Take difference between filter and orig data
        difference = np.abs(x.to_series() - temp)
        # Find those data values that the diff was less than or equal to the user supplied threshold
        return x.where(difference <= threshold)

# Convert all precipitation from cummulative to incremental
test_plots = False

# Aggregate to daily using median of cummulative precipitation, skip missing values
# If only 1 value per day, it will use this
dly_cum_precip = ds['CummulativePrecipitationA'].resample(freq='D',
                       dim='Time_UTC',how='mean',label='right',skipna=True)
if test_plots:
    plt.figure()
    plt.plot(ds.Time_UTC, ds.CummulativePrecipitationA)
    plt.plot(dly_cum_precip.Time_UTC, dly_cum_precip)

# Difference to get daily increments
dly_inc_precip = dly_cum_precip.diff(dim='Time_UTC')
# Set negative values to 0 (have to fill all nan with 0, then fill in orign nan, update with new xarray...)
# TODO: fix where with new xarray
c_notnull = dly_inc_precip.notnull()
dly_inc_precip = dly_inc_precip.where(dly_inc_precip >= 0)
dly_inc_precip.fillna(0)
dly_inc_precip.where(c_notnull)

if test_plots:
    plt.figure()
    plt.plot(dly_inc_precip.Time_UTC, dly_inc_precip)

# Downsample back to original time step (hourly)
h_per_day = 24
dly_inc_precip = dly_inc_precip / h_per_day # reduce daily rate so we can easily upsample to hourly
# hrl_inc_precip = dly_inc_precip.resample(freq='H',
#                      dim='Time_UTC', how='mean', label='right', skipna=True, method='bfill')
# hrl_inc_precip = dly_inc_precip.resample(Time_UTC='H', method='bfill', dim='Time_UTC').mean()
hrl_inc_precip = dly_inc_precip.reindex_like(ds['IncrementalPrecipitationA'], method='backfill')
if test_plots:
    plt.figure()
    plt.plot(hrl_inc_precip.Time_UTC, hrl_inc_precip)
    plt.show()

# Merge with existing incremental precipitation data
current_inc_precip = ds.IncrementalPrecipitationA
#print(current_inc_precip.sum(dim='Time_UTC').values)
# Set stations with majority missing data to nan
# Use combine_first() so that any existing incremental precip data is not overwritten
ds['IncrementalPrecipitationA'] = current_inc_precip.combine_first(hrl_inc_precip)
#print(ds['IncrementalPrecipitationA'].sum(dim='Time_UTC').values)

# Quality Control (Hourly)

# Max and min (inclusive)
min_limits = {'WindDirectionatA':-0, 'ScalarWindSpeedA':-0, 'AirMoistureContentA':5,'SnowWaterEquivelentA':-0, 'SnowDepthA':-0, 'IncrementalPrecipitationA':-0, 'AirtemperatureA':-40}
max_limits = {'WindDirectionatA':360, 'ScalarWindSpeedA':30, 'AirMoistureContentA':100,'SnowWaterEquivelentA':3, 'SnowDepthA':5.5, 'IncrementalPrecipitationA':0.06, 'AirtemperatureA':50}

#print(ds['IncrementalPrecipitationA'].mean())

for cvar in min_limits.keys():
    print('QC-min-max: '+str(cvar))
    print('Start missing ',ds[cvar].isnull().sum().values)
    ds[cvar] = QC_min_max(ds[cvar], min_limits[cvar], max_limits[cvar])
    print('End missing ',ds[cvar].isnull().sum().values)

#print(ds['IncrementalPrecipitationA'].notnull().sum(dim='Time_UTC').values)
#print(ds['IncrementalPrecipitationA'].sum(dim='Time_UTC').values)

# ROC - Use median filter to find values
# Units are standard meteric (C, m)
ROC_thress = {'AirMoistureContentA':60,
              'SnowWaterEquivelentA':0.2, 
              'SnowDepthA':0.5, 
              #'CummulativePrecipitationA':20/1000, 
              'AirtemperatureA':10}

# Units are timestep (currenlty only hours)
ROC_window = {'AirMoistureContentA':6,
              'SnowWaterEquivelentA':4, 
              'SnowDepthA':4, 
              #'CummulativePrecipitationA':48, 
              'AirtemperatureA':6} # dt (hrs)

for cvar in ROC_thress.keys():
    print('QC-ROC: '+str(cvar))
    ds[cvar] = QC_ROC(ds[cvar], ROC_thress[cvar], ROC_window[cvar]) 


#DS = '2012-10'
#DE = '2013-09'

# In[ ]:

#plt.plot(ds.Time_UTC.sel(Time_UTC=slice(DS,DE)),ds.SnowWaterEquivelentA.sel(Time_UTC=slice(DS,DE)).values);


# In[ ]:

#ds.AirMoistureContentA.plot.hist(bins=1000);


# In[ ]:

#plt.plot(ds.Time_UTC.sel(Time_UTC=slice(DS,DE)),ds.AirMoistureContentA.sel(Time_UTC=slice(DS,DE)).values);


# In[ ]:

#ds.ScalarWindSpeedA.plot.hist(bins=1000);


# In[ ]:

#plt.plot(ds.Time_UTC.sel(Time_UTC=slice(DS,DE)),ds.ScalarWindSpeedA.sel(Time_UTC=slice(DS,DE)).values);


# In[ ]:

#ds.WindDirectionatA.plot.hist(bins=1000);


# In[ ]:

#plt.plot(ds.Time_UTC.sel(Time_UTC=slice(DS,DE)),ds.WindDirectionatA.sel(Time_UTC=slice(DS,DE)).values);


# In[ ]:

#ds.SnowDepthA.plot.hist(bins=500);


# In[ ]:

#plt.plot(ds.Time_UTC.sel(Time_UTC=slice(DS,DE)),ds.SnowDepthA.sel(Time_UTC=slice(DS,DE)).values);


# In[ ]:

#plt.plot(ds.Time_UTC.sel(Time_UTC=slice(DS,DE)),ds.AirtemperatureA.sel(Time_UTC=slice(DS,DE)).values);


# In[ ]:




# In[ ]:

#plt.plot(ds.Time_UTC.sel(Time_UTC=slice(DS,DE)),ds.CummulativePrecipitationA.sel(Time_UTC=slice(DS,DE)).values);


# In[ ]:

#(ds.IncrementalPrecipitationA.where(ds.IncrementalPrecipitationA>0,drop=True)*1000).plot.hist(bins=100);


# In[ ]:

#plt.plot(ds.Time_UTC, ds.IncrementalPrecipitationA.cumsum(dim='Time_UTC').values*1000);
# plt.plot(ds.Time_UTC.sel(Time_UTC=slice(DS,DE)), ds.IncrementalPrecipitationA.sel(Time_UTC=slice(DS,DE)).values*1000);


# In[ ]:

#plt.plot(ds.Time_UTC.sel(Time_UTC=slice(DS,DE)), ds.IncrementalPrecipitationA.sel(Time_UTC=slice(DS,DE)).cumsum(dim='Time_UTC').values);


# In[ ]:

# Save as netcdf file
ds.to_netcdf(netcdf_file_out)
print(netcdf_file_out)


