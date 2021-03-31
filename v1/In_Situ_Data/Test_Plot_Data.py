import imp
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import os
import seaborn as sns
import sys
import xarray as xr

plt.rcParams.update({'figure.max_open_warning': 0})


ds_m = xr.open_dataset(r'/media/data2/SnowCast_station_data/merged/Hourly_Merged.nc')
ds_q = xr.open_dataset(r'/media/data2/SnowCast_station_data/QC/Hourly_QC.nc')

# General plotting settings
sns.set_style('ticks')
sns.set_context("talk", font_scale=1.5, rc={"lines.linewidth": 2.5})

# time
#ds_m = ds_m.sel(Time_UTC=slice("2014-10-01","2017-09-28"))
#ds_q = ds_q.sel(Time_UTC=slice("2014-10-01","2017-09-28"))

# vars_to_plot = ['SnowWaterEquivelentA','SnowDepthA','AirtemperatureA']
vars_to_plot = ['IncrementalPrecipitationA']
network = 'ABE_AGG_HIST'
# network = 'CRHO'
# network = 'all'

print(set(ds_m.network.values))
ds_m = ds_m[vars_to_plot]
ds_q = ds_q[vars_to_plot]

if network!='all':
    ds_m = ds_m.where(ds_m.network==network, drop=True)
    ds_q = ds_q.where(ds_q.network==network, drop=True)

for cvar in vars_to_plot:

    plt.figure()
    plt.title('Merged')
    #plt.plot(ds_m.Time_UTC, ds_m[cvar].sel(staID=['05BJ805' ,'05CA805' ,'2A32P' ,'2C14P' ,'PWL']))
    X = ds_m[cvar]
    for csta in X.staID:
        plt.plot(X.Time_UTC, X.sel(staID=csta),
                 label=X.sel(staID=csta).station_name.values)
    plt.legend()

    plt.figure()
    plt.title('QC')
    #plt.plot(ds_q.Time_UTC, ds_q[cvar].sel(staID=['05BJ805' ,'05CA805' ,'2A32P' ,'2C14P' ,'PWL']))
    Y = ds_q[cvar]
    for csta in Y.staID:
        plt.plot(Y.Time_UTC, Y.sel(staID=csta),
                 label=Y.sel(staID=csta).station_name.values)
    plt.legend()

plt.show()


