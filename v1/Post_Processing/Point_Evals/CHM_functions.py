import numpy as np
import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import xarray as xr

# Save Figure
def save_figure(f,file_out,fig_res):


    f.savefig(file_out,bbox_inches='tight',dpi=fig_res)

# Function that makes two data sets common:
def make_common(ds_obs, ds_mod, dt_eval, dt_eval_hr,
                remove_missing=True, percent_nan_allowed=20,
                exclude_forest=2, forest_staID=None):
    # In case data sets came from python 2.7 and 3.5, remove bytes
    # TODO: instead of decoding, throw error if ds_obs and ds_mod were not created in the same python
    # environent (i.e. 2.7 and 2.7).
    '''def decode_strs(ds):

        for cvar in ['station','station_name','network']:
            if cvar in ds: # Model does not have station_name or network coords
                if ds[cvar].dtype!='object':
                    ds[cvar] = np.array([x.decode("utf-8") for x in ds[cvar].values])
        return ds

    ds_obs = decode_strs(ds_obs)
    ds_mod = decode_strs(ds_mod)
    '''
    # dt_eval = 'H' # MS (month start), H (hour), W (week)
    # How do we handel missing values within an aggregation period?
    # We use a threshold (percent_nan_allowed) for % missing within a period,
    skipna = True # Skips nans when doing aggregation, then we remove those periods with less than percent_nan_allowed

    # (Optional) drop stations based on vegetation setting
    # Get MODEL forested stations (could be different than reality!!!)
    if 'snow_load' in ds_mod:
        for_mod_sta = ds_mod.where(ds_mod.snow_load.max(dim='time') > 0, drop=True).station.values
    else:
        raise ValueError("No forested stations in model run.")

    # Check obs and model both think the same stations are forested!
    assert set(forest_staID) == set(for_mod_sta)

    # Optional exclude/include forested sites
    if exclude_forest == 0:  # exclude forest
        print("Dropping forested stations...")
        ds_obs = ds_obs.sel(station=list(set(ds_obs.station.values) - set(forest_staID)))
        ds_mod = ds_mod.sel(station=list(set(ds_mod.station.values) - set(forest_staID)))
    elif exclude_forest == 1:  # forest only
        print("Only using forested stations...")
        ds_obs = ds_obs.sel(station=forest_staID)
        ds_mod = ds_mod.sel(station=forest_staID)
    elif exclude_forest == 2:  # Use all stations (do nothing)
        print("Using forested and non-forested stations...")
    else:
        raise ValueError('Not a valid option')

    # Common stations
    obs_sta = ds_obs['station'].values
    mod_sta = ds_mod['station'].values

    # Find common stations
    com_sta = np.sort(list(set(obs_sta).intersection(mod_sta)))
    print("Common stations are:", com_sta)
    print("")
    if not len(com_sta):
        print(obs_sta)
        print(mod_sta)
        raise ValueError('No common stations found')

    # Extract only common stations
    ds_obs = ds_obs.sel(station=com_sta)
    ds_mod = ds_mod.sel(station=com_sta)

    # Common variables
    obs_vars = ds_obs.data_vars
    mod_vars = ds_mod.data_vars
    # Find common variables
    com_vars = np.sort(list(set(obs_vars).intersection(mod_vars)))
    # Extract only common vars
    ds_obs = ds_obs[com_vars]
    ds_mod = ds_mod[com_vars]
    print("Common variables are:", com_vars)
    print("")

    # Pre-trim time to common time start and end (speeds up time step aggregation)
    T_start = np.max([ds_mod.time.values[0], ds_obs.time.values[0]])
    T_end = np.min([ds_mod.time.values[-1], ds_obs.time.values[-1]])
    print(T_start, T_end)
    ds_obs = ds_obs.where((ds_obs.time >= T_start) & (ds_obs.time <= T_end), drop=True)
    ds_mod = ds_mod.where((ds_mod.time >= T_start) & (ds_mod.time <= T_end), drop=True)

    # Common time step
    def agg_time(ds_IN, dt_eval, dt_eval_hr, percent_nan_allowed):

        dt_in = (ds_IN.time.values[2] - ds_IN.time.values[1]).astype('timedelta64[h]').astype(float)

        if ((dt_in != dt_eval_hr[dt_eval]) & (
            dt_eval != 'exact')):  # Check if we need to agg (exact skips agg (i.e. snow surveys))
            print('Resampling')

            # Aggregate
            # TODO: this behaves different on python 2.7 and 3.5, don't know why....
            ds_OUT = ds_IN.resample(freq=dt_eval, dim='time', how='mean', label='left', skipna=skipna)

            # Aggregate booleans of not missing, to get fraction in agg period not missing
            obs_fraction_OK = ds_IN.notnull().resample(freq=dt_eval, dim='time', how='mean', label='left')
            if 'p' in ds_IN.data_vars:
                ds_OUT['p'] = ds_IN['p'].resample(freq=dt_eval, dim='time', how='sum', label='left', skipna=skipna)

            # Drop values where fraction exceeds the threshold
            ds_OUT = ds_OUT.where(obs_fraction_OK >= (1-percent_nan_allowed/100) )

        else:
            ds_OUT = ds_IN
        return ds_OUT

    obs_dt_val = agg_time(ds_obs, dt_eval, dt_eval_hr, percent_nan_allowed)
    mod_dt_val = agg_time(ds_mod, dt_eval, dt_eval_hr, percent_nan_allowed)
    # print(obs_dt_val.p.sum(dim='time'))
    # Common non-Missing data (optional)
    if remove_missing:
        print("Removing missing observed timesteps from model")
        I_not_null = (mod_dt_val.notnull()) & (obs_dt_val.notnull())
        mod_dt_val = mod_dt_val.where(I_not_null)
        obs_dt_val = obs_dt_val.where(I_not_null)

    return (obs_dt_val, mod_dt_val)

# Calc bias between two DataSets (assumes they have been "commoned" using make_common()
def calc_bias(ds_obs, ds_mod, cvar):


    if cvar == 'p': # Cummulative variables (p is incremental)
        x = (ds_mod[cvar] - ds_obs[cvar]).sum(dim='time')/ds_obs[cvar].sum(dim='time')*100
    else:
        return ds_mod[cvar].mean(dim='time') - ds_obs[cvar].mean(dim='time')

# Calc RMSE between two DataSets (assumes they have been "commoned" using make_common()
def calc_rmse(ds_obs, ds_mod, cvar):
    # calculate squared errors
    se = (ds_mod[cvar] - ds_obs[cvar])**2.0
    # calculate root-mean-squared errors averaged over all stations
    return xr.ufuncs.sqrt(se.mean(dim=['time']))

# Calculate R2
def calc_r2(ds_obs, ds_mod, cvar):
    # total sum of squares
    SStot = ( (ds_obs[cvar] - ds_obs[cvar].mean(dim='time') )** 2.0).sum(dim='time')

    # residual sum of squares:
    SSres = ( (ds_obs[cvar] - ds_mod[cvar]) ** 2.0).sum(dim='time')

    return (1 - SSres / SStot)

# Plot a metric on a map
def plot_point_metric(dem, da_metric, variable_name, variable_units, cmap_in, ctype):
    fig = plt.figure(figsize=(20, 12))
    ax1 = plt.axes(projection=ccrs.AlbersEqualArea())
    ax1.imshow(np.flipud(dem.values), extent=[np.min(dem.x), np.max(dem.x),
                                              np.min(dem.y), np.max(dem.y)], aspect=ax1.get_aspect())
    # Add metric values at points
    p1 = ax1.scatter(da_metric.Lon, da_metric.Lat, transform=ccrs.AlbersEqualArea(), s=100,
                c=da_metric, zorder=100,
                cmap=cmap_in)  # yc, xc -- lists or numpy arrays
    # Add a colorbar
    c1 = fig.colorbar(p1)
    c1.ax.set_ylabel(variable_name+' '+ctype+' ('+variable_units+')')
    plt.title(variable_name)

    return fig
