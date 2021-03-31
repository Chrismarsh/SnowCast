import glob
import imp
import numpy as np
import os
import pandas as pd
import seaborn as sns
import sys
import wget
import xarray as xr

sns.set_context("talk",font_scale=1.5)
sns.set_style('whitegrid')
# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) == 1:
    raise ValueError('Requires one argument [configuration file]')

# Get name of configuration file/module
configfile = sys.argv[-1]

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
data_dir = X.data_dir
git_dir   = X.git_dir

# Aggregate to different periods

# https://www.eol.ucar.edu/content/wind-direction-quick-reference
# Convert wind speed and direction to u/v components
def WS_Wdir_2_U_V(obs_wdr,obs_ws):
    import numpy as np
    RperD = (np.pi / 180.0)
    obs_U = -1 * obs_ws * np.sin(obs_wdr*RperD)
    obs_V = -1 * obs_ws * np.cos(obs_wdr*RperD)
    return (obs_U,obs_V)

# Convert U and V components to Wdir and Wind speed
def U_V_2_WS_Wdir(U,V):
    import numpy as np
    DperR = (180.0 / np.pi)
    Wdir = (np.arctan2(-1*U,-1*V) * DperR)%360 # needed to take modulus of 360
    WS   = np.sqrt(np.power(U,2)+np.power(V,2))
    return (WS,Wdir)

# Average WS and Wdir by component method
def avg_Ws_Wdir(obs_wdr,obs_ws,dt_freq):
    # Convert to U V
    (obs_U,obs_V) = WS_Wdir_2_U_V(obs_wdr,obs_ws)
    # Take average of components
    obs_U_agg = obs_U.resample(freq=dt_freq,dim='Time_MST',how='mean',label='right')
    obs_V_agg = obs_V.resample(freq=dt_freq,dim='Time_MST',how='mean',label='right')
    # Convert back to WS and Wdir
    (obs_ws_OUT,obs_wdir_OUT) = U_V_2_WS_Wdir(obs_U_agg,obs_V_agg)
    return (obs_ws_OUT,obs_wdir_OUT)

# Data network
network = 'CRHO_NRT'
download_dir = os.path.join(data_dir,network,'current')

# Netcdf file to save to
netcdf_dir   = os.path.join(data_dir,network,'netcdf')
# Make if does not exist
if not os.path.exists(netcdf_dir):
    os.makedirs(netcdf_dir)
netcdf_file_out =  os.path.join(netcdf_dir,'CRHO_NRT.nc')

# Ascii files are downloaded as Station_name__Variable_name
os.chdir(download_dir)
all_files = glob.glob('*.csv')

# Get station and variable names
all_sta = []
all_var = []
for cf in all_files:
    fname = cf.split('.')[0]
    sta_name, var_name = fname.split('__')
    all_sta.append(sta_name)
    all_var.append(var_name)
# Get unique
all_sta = list(set(all_sta))
all_var = list(set(all_var))

# Import files
ds_list = []
for csta in all_sta:

    da_list = [] # list to store all variables for this station_w

    for cvar in all_var:

        cf=csta+'__'+cvar+'.csv'
        if not os.path.isfile(os.path.join(download_dir,cf)):
            continue
        print(cf)

        # Load in to python
        # 2017-09-30 17:00:00
        dateparse = lambda x: pd.datetime.strptime(x, '%Y-%m-%d %H:%M:%S')
        try: # Because sometimes the file exists, but is empty
            df = pd.read_csv(cf, index_col=1, engine='python',
                             parse_dates=True, date_parser=dateparse, na_values=['NA','no value'])
            if df.shape[0]==0:
                continue
        except:
            print("Could not parse "+cf+". Something wrong with file format.")
            continue
        df.index.names = ['Time_MST']
        s = df.ix[:, 1] # Select variable (becomes a Series)
        s.name = cvar
        da = xr.DataArray.from_series(s)
        # Store
        da_list.append(da)

    # Merge into dataset
    ds = xr.merge(da_list)
    ds.coords['station_w'] = csta

    # Fill in Dummy variables
    for tvar in all_var:
        if not tvar in ds.data_vars:
            # Fill it
            ds[tvar] = xr.DataArray(ds[ds.data_vars.keys()[0]]*np.NaN,
                                    coords={'Time_MST':ds.Time_MST}, dims=('Time_MST'))

    # Store in list
    ds_list.append(ds)

# Concat by stations
ds_all = xr.concat(ds_list,dim='station_w')

# Add metadata (steal from CRHO HIST file

# Dictionary to go from wiski station name to Snowcast "station_name"
wiski_2_snowcast = {'Fortress_Ridge':"Fortress Ridge",'Vista_View':"Vista View",
                    "Bonsai_Meteorological":"Bonsai","Burstall_Pass":"Burstall Pass",
                    "Centennial_Ridge":"Centennial Ridge",
                    "Canadian_Ridge":"Canadian Ridge", "Fortress_Ledge":"Fortress Ledge",
                    "Fortress_Ridge_South_Meteorological":"Fortress Ridge South",
                    "Fisera_Ridge":"Fisera Ridge","Helen":"Helen Lake","Hay_Meadow":"Hay Meadows",
                    "Peyto_Hut_Main":"Peyto","Upper_Clearing":"Upper Clearning",
                    "Canadian_Ridge_North":"Canadian Ridge North"}
ds_all['station_name'] = [wiski_2_snowcast[x] for x in ds_all.station_w.values]

# Load in Hist to "steal" metadata
CRHO = os.path.join(data_dir, 'CRHO_HIST', 'netcdf', 'CRHO_1hour.nc') # MST
ds_CRHO = xr.open_dataset(CRHO)
ds_CRHO = ds_CRHO['AirtemperatureA']

# Add station (staID)
ds_all['station'] = [ds_CRHO.where(ds_CRHO.station_name==x,drop=True).station.item() for x in ds_all['station_name']]
# Set index to be station
ds_all['station_w'] = ds_all['station']
ds_all = ds_all.drop(['station'])
ds_all.rename({'station_w':'station'},inplace=True)
# Add info
ds_all.coords['Lat'] = xr.DataArray([ds_CRHO.where(ds_CRHO.station_name==x,drop=True).Lat.item() for x in ds_all['station_name']],
                             coords={'station':ds_all.station}, dims=('station'))
ds_all.coords['Lon'] = xr.DataArray([ds_CRHO.where(ds_CRHO.station_name==x,drop=True).Lon.item() for x in ds_all['station_name']],
                             coords={'station':ds_all.station}, dims=('station'))
ds_all.coords['Elevation'] = xr.DataArray([ds_CRHO.where(ds_CRHO.station_name==x,drop=True).Elevation.item() for x in ds_all['station_name']],
                             coords={'station':ds_all.station}, dims=('station'))
ds_all.coords['network'] = xr.DataArray([ds_CRHO.where(ds_CRHO.station_name==x,drop=True).network.item() for x in ds_all['station_name']],
                             coords={'station':ds_all.station}, dims=('station'))
ds_all.coords['station_name'] = xr.DataArray([ds_CRHO.where(ds_CRHO.station_name==x,drop=True).station_name.item() for x in ds_all['station_name']],
                             coords={'station':ds_all.station}, dims=('station'))
# Fix variable names
w_2_s_vars = {'TEMPERATURE_AIR':'AirtemperatureA',
              'AccumulatedPrecip':'CummulativePrecipitationA',
             'IntervalPrecip':'IncrementalPrecipitationA' ,
             'IncomingSWRad':'DownwardSolarRadiation',
             'WindDir':'WindDirectionatA',
             'WindSpeed':'ScalarWindSpeedA',
             'SnowDepth':'SnowDepthA',
             'RelHum':'AirMoistureContentA',
             'OutgoingSWRad':'UpwardSolarRadiation',
             'IncomingLWRad':'DownwardTerrestrialRad',
             'OutgoingLWRad':'UpwardTerrestrialRad',
             'SurfTemp':'tsrf'}
ds_all.rename(w_2_s_vars, inplace=True)

# Units to standard metric
ds_all['IncrementalPrecipitationA'] = ds_all.IncrementalPrecipitationA / 1000.0 # mm to m
ds_all['CummulativePrecipitationA'] = ds_all.CummulativePrecipitationA / 1000.0 # mm to m

# Aggregate from 15 min to 1 hour
# Aggregate (allow a fraction of missing period)
percent_nan_allowed = 26  # (one 15 min out of an hour)
skipna = True  # Skips nans when doing aggregation, then we remove those periods with less than percent_nan_allowed
dt_out = 'H'

# Aggregate booleans of not missing, to get fraction in agg period not missing
obs_fraction_OK = ds_all.notnull().resample(freq=dt_out, dim='Time_MST', how='mean', label='right')

# TODO: this behaves different on python 2.7 and 3.5, don't know why....
ds_1hr = ds_all.resample(freq=dt_out, dim='Time_MST', how='mean', label='right', skipna=skipna)

# For variables where we need to take the sum over the agg period
for xvar in ['IncrementalPrecipitationA', 'IncrementalPrecipitationB', 'IncrementalPrecipitationC']:
    if xvar in ds_1hr:
        ds_1hr[xvar] = ds_all[xvar].resample(freq=dt_out, dim='Time_MST', how='sum', label='right',
                                       skipna=skipna).T  # Transpose needed

# For variables where we need to take the median over the agg period
for xvar in ['SnowDepthQCvalue']:
    if xvar in ds_1hr:
        ds_1hr[xvar] = ds_all[xvar].resample(freq=dt_out, dim='Time_MST', how='median', label='right').T  # Transpose needed

# Wind speed component average
(obs_ws_D, obs_wdir_D) = avg_Ws_Wdir(ds_all['WindDirectionatA'], ds_all['ScalarWindSpeedA'], dt_out)
ds_1hr['WindDirectionatA'] = obs_wdir_D.T  # Transpose needed
ds_1hr['ScalarWindSpeedA'] = obs_ws_D.T  # Transpose needed

# Drop values where fraction exceeds the threshold
ds_1hr = ds_1hr.where(obs_fraction_OK >= (1 - percent_nan_allowed / 100))

# To netcdf
ds_1hr.to_netcdf(netcdf_file_out)

# # Test plot
# import matplotlib.pyplot as plt
# for cvar in ds_all.data_vars:
#     plt.figure()
#     for csta in ds_all.station_w:
#         if ds_all[cvar].sel(station_w=csta).notnull().sum()>0:
#             plt.plot(ds_all.Time_MST, ds_all[cvar].sel(station_w=csta))

