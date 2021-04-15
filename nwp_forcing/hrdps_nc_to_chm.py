import glob
import numpy as np
import os
import pandas as pd
import re
import xarray as xr


def preprocess(x, settings, keep_forecast=False):

    print(f'nc = {x.datetime[0].values}')


    if len(x.datetime) < 48:
        raise Exception(f'Expected a nc with 48 timesteps. nc start = {x.datetime[0].values}')

    nc_start_hour = pd.to_datetime(x.datetime.values[0], format='%Y-%m-%dT%H:%M:%S').hour
    if nc_start_hour > 1:
        raise Exception(f'Start hour is later than 1am and will break the indexing. Double check this is what you want. nc start = {x.datetime[0].values}')

    # standard mode, we aren't the last item, so throw away the +24h forecast
    # this skips the first timestep because the accumulated values in that timestep are NaN and we can't use them
    # So if we have a 1am this grabs 2am -> 1am + 1day
    start_idx = 1
    stop_idx = 25

    if keep_forecast:
        start_idx = 25
        stop_idx = 48

    # if we start at 1am, we need to shift the index back by one
    # if nc_start_hour == 1:
    #     start_idx -= 1
    #     # stop_idx -= 1
    #
    #     if keep_forecast:
    #         start_idx -= 1
    #         stop_idx -= 1

    x = x.isel(datetime=np.arange(start_idx, stop_idx))

    # really here for concating legacy nc files from Snowcast v1
    try:
        x = x.rename_vars({'HGT_P0_L1_GST0': 'HGT_P0_L1_GST'})
    except ValueError as e:
        pass

    # snowcast v2 nc come with an extra time coord
    try:
        x = x.drop('time')
    except ValueError as e:
        pass

    # we may have nc files created from a different set of grib and thus the variables in each nc might not match
    # across all nc files. Drop anything that isn't explicitly requested/needed for CHM
    data_vars_to_drop = set([f for f in x.data_vars]) - set([name for name in settings['hrdps2chm_names'].values()])
    x = x.drop(data_vars_to_drop)

    isnan = np.isnan(x.max())
    for v in isnan.data_vars:
        if isnan[v]:
            print(f'In file {x.datetime[0].values}, variable {v} has NaN values!')

    # we need to check if we need to subtract 360 from the longitude values.
    # !!!!!!  Snowcast currently assumes we are in the western hemisphere !!!!!!!!
    # so,
    # TODO: Have a better robustness check here. Maybe depending on the data source?
    if x.gridlon_0.min().values > 180:
        x['gridlon_0'] = x.gridlon_0 - 360

    if x.gridlon_0.dtype == np.dtype('float64'):
        x['gridlon_0'] = x.gridlon_0.astype('float32')

    if x.gridlat_0.dtype == np.dtype('float64'):
        x['gridlat_0'] = x.gridlat_0.astype('float32')

    return x


def hrdps_nc_to_chm(settings):
    # Get all file names
    all_files = glob.glob(os.path.join(settings['nc_ar_dir'], '*.nc'))
    date = []
    fname = []
    for f in all_files:
        p = re.compile('([0-9]{4}-[0-9]{2}-[0-9]{2})')
        m = p.search(f)

        d = pd.to_datetime(m.group(1), format='%Y-%m-%d')
        date.append(d)
        fname.append(f)

    df = pd.DataFrame({'date': date, 'file': fname})
    df = df.sort_values(by=['date'])
    df = df.reset_index()

    if len(df) == 0:
        raise Exception(f"There are no nc files in {settings['nc_ar_dir']}, ensure you have run grib2nc.")

    start = df.date[0].strftime('%Y-%m-%d')

    try:
        if settings['start_date'] is not None:
            start = pd.to_datetime(settings['start_date'], format='%Y-%m-%d')
            df = df[ df.date >= start]

            if len(df) == 0:
                raise Exception(f"No files were selected based on your start date of {start}. Ensure it is correct.")
    except KeyError as e:
        pass

    end = df.date.iloc[-1].strftime('%Y-%m-%d')

    try:
        if settings['end_date'] is not None:
            end = pd.to_datetime(settings['end_date'], format='%Y-%m-%d')
            df = df[df.date <= end]

            if len(df) == 0:
                raise Exception(f"No files were selected based on your end date of {end}. Ensure it is correct.")
    except KeyError as e:
        pass

    diff = pd.date_range(start=start,
                         end=end,
                         freq='1d').difference(df.date)
    if len(diff) > 0:
        missing = '\n'.join([str(d) for d in diff.to_list()])
        raise Exception(f'Missing the following dates:\n {missing}')

    # this is everything not including +24hr forecase
    ar_nc_path = os.path.join(settings['nc_chm_dir'], f'HRDPS_West_current.nc')
    forecast_nc_path = os.path.join(settings['nc_chm_dir'], f'HRDPS_West_forecast.nc')

    update_nc = False  # are we just going to update/append to an existing nc or regen the whole thing?
    if os.path.exists(ar_nc_path) and not settings['force_nc_archive']:
        update_nc = True
        print('Updating existing nc archive...')
        existing_ar = xr.open_dataset(ar_nc_path,
                                      engine='netcdf4')

        # get time coverage of existing
        # we will have the first time step (00h) of the next day, so ignore _that_ and get the actual complete last day
        end = existing_ar.datetime.values[-2]

        # only keep the input nc to append
        df = df[df.date > end]

        existing_ar.close()
        if len(df) == 0:
            print(f"Existing archive has end date {end}, which matches most recent .nc chunks. No update needed")
            return True

    ds = xr.open_mfdataset(df.file.tolist(),
                           concat_dim='datetime',
                           engine='netcdf4',
                           parallel=False,
                           preprocess=lambda x: preprocess(x, settings))

    # if we have mixed 00h and 01h start times, we will have 1 duplicate timestep as we cross that bound
    _, index = np.unique(ds['datetime'], return_index=True)

    ndup = len(ds.datetime) - len(index)
    if ndup > 0:
        ds = ds.isel(datetime=index)
        print(f'Dropped {ndup} duplicate timesteps after merge. This results from mixing 00h and 01h start times.')

    forecast = xr.open_mfdataset(df.file.tolist()[-1],
                                 concat_dim='datetime',
                                 engine='netcdf4',
                                 parallel=False,
                                 preprocess=lambda x: preprocess(x, settings, keep_forecast=True))

    # write out the archive
    if update_nc:
        existing_ar = xr.open_mfdataset([ar_nc_path],
                                        engine='netcdf4')
        # update our archive of non-forecasts
        ds = xr.concat([existing_ar, ds],
                       dim="datetime")

        ds.to_netcdf(ar_nc_path + '.tmp',
                     engine='netcdf4'
                     )
        os.remove(ar_nc_path)
        os.rename(ar_nc_path + '.tmp', ar_nc_path)
    else:
        ds.to_netcdf(ar_nc_path,
                     mode='w',
                     engine='netcdf4'
                     )

    ds = xr.concat([ds, forecast],
                   dim="datetime")

    try:
        os.remove(forecast_nc_path)
    except OSError as e:
        pass

    ds.to_netcdf(forecast_nc_path,
                 engine='netcdf4'
                 )

    return True
