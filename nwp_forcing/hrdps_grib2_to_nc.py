
import glob
import os
import pandas as pd
import re
import xarray as xr
from tqdm import tqdm


def preprocess(x):

    if len(x.data_vars) >1:
        raise Exception('More than 1 data data_var in grib file')

    x = x.expand_dims('valid_time')

    try:
        x = x.drop('heightAboveGround')
    except ValueError as e:
        pass
    try:
        x = x.drop('surface')
    except ValueError as e:
        pass

    try:
        x = x.drop('step')
    except ValueError as e:
        pass

    try:
        x = x.drop('time')
    except ValueError as e:
        pass

    try:
        x = x.rename_vars({'HGT_P0_L1_GST0': 'HGT_P0_L1_GST'})
    except ValueError as e:
        pass

    return x


def load_GEM_4d_var(PresLevs, UA_files):
    ds_UA = xr.Dataset()
    for cP in PresLevs:
        # Get all time step files for this pressure level
        cfiles = [x for x in UA_files if '_' + cP in x]  # Underscore needed to exclude patterns in date

        ds = xr.open_mfdataset(cfiles,
                                 # concat_dim='valid_time',
                                 # data_vars='minimal',
                                 # coords='minimal',
                                 preprocess=lambda x: preprocess(x),
                                 parallel=True,
                                 engine='cfgrib')

        ds = ds.expand_dims('isobaricInhPa')
        # Combine
        ds_UA = xr.merge([ds_UA, ds])

    return ds_UA


def hrdps_grib2nc(settings):

    if not os.path.exists(settings['grib_dir']):
        var = settings['grib_dir']
        raise Exception(f'Download directory: {var} does not exist')

    #build up a list of all the files, for each variable we will need to build
    print('Enumerating input grib2')


    hrdps_files = {}

    # list of the paths of the nc files we processed.
    # Required for the checkpointing code
    processed_nc_files = []

    # we need to ensure that if we are looking for grib files to process we have everything asked for in hrdps
    # thus we need the two passes
    have_files_to_process = False
    files = glob.glob( os.path.join(settings['grib_dir'],'*.grib2'))
    if len(files) != 0:
        have_files_to_process = True

    if have_files_to_process:
        for var in settings['hrdps_variables']:
            # print(var)
            files = glob.glob( os.path.join(settings['grib_dir'],f'*_{var}_*.grib2'))

            date = []
            P = []
            fname = []
            v = []

            if len(files) == 0:
                raise Exception(f'We are processing grib files but are missing grib files for {var}')

            for f in files:
                p = re.compile('([0-9]{8}T[0-9]{2}).+_PT([0-9]{3})H')
                m = p.search(f)

                d = pd.to_datetime(m.group(1), format='%Y%m%dT%H')
                date.append(d)
                P.append(int(m.group(2)))
                fname.append(f)
                v.append(var)

            jd = pd.DatetimeIndex(date).to_julian_date().values

            df = pd.DataFrame({'date':date, 'P':P,'file':fname,'jd':jd,'var':v})
            df = df.sort_values(by=['date','P'])
            df = df.reset_index()
            df = df.drop(['index'],axis=1)


            df = df[ df['date'].dt.hour == 0] # only deal with the midnight forecasts for now
            # at this point we have all the files, however we want to discard the 12hr+ forecast if we have the next day's
            # archive = df[ df['P'] < 24 ]
            # forecast = df[ (df['P'] > 23) & (df['date'] == df['date'].max()) ]
            # df = pd.concat([archive, forecast])

            hrdps_files[var]=df


        # enables outputting what variables go with what gribs
    #     d = xr.open_dataset(files[0],engine='cfgrib')
    #     data_vars= [f for f in d.data_vars][0]
    #     print(f'\'{var}\':\'{data_vars}\'')
    # exit(0)
    if len(hrdps_files) == 0:
        print('No grib2 files found to process')
        return False, None

    hrdps_files = pd.concat(hrdps_files)

    if len(hrdps_files) == 0:
        print('No grib2 files found to process')
        return False, None

    # import and combine all grib2 files
    print('Opening all grib2 data files')

    # Presure levels to extract air temperature from
    PresLevs = ['1015', '1000', '0985', '0970', '0950', '0925', '0900']


    for doy in tqdm(hrdps_files.jd.unique()):

        # engine=python is required to avoid this issue
        # > For the poeple wondering why this bug appears for them and not for others (or vice versa):
        # > If you do not have the numexpr package installed, then python will be automatically used as engine. Thus, you do not need to specify engine='python' in the query method.
        # https://github.com/pandas-dev/pandas/issues/34251#issuecomment-732769686
        files = hrdps_files.query('jd == @doy & not var.str.contains(\'TMP_ISBL\') & not var.str.contains(\'HGT_ISBL\') ',engine='python').file.tolist()

        d = pd.to_datetime(doy, origin='julian',unit='D')


        ds = xr.open_mfdataset(files,
                               # concat_dim='valid_time',
                               # combine='nested',
                               # data_vars='minimal',
                               # coords='minimal',
                               # compat='override',
                               preprocess=lambda x: preprocess(x),
                               parallel=True,
                               engine='cfgrib')

        UA_TMP = hrdps_files.query('jd == @doy & var.str.contains(\'TMP_ISBL\')',engine='python').file.tolist()
        ds_UA_T = load_GEM_4d_var(PresLevs, UA_TMP)

        UA_HGT = hrdps_files.query('jd == @doy & var.str.contains(\'HGT_ISBL\')',engine='python').file.tolist()
        ds_UA_HGT = load_GEM_4d_var(PresLevs, UA_HGT)

        ds_UA = xr.merge([ds_UA_T, ds_UA_HGT])

        # Approx method of calculating lapse rate (diff from lower and upper atmos temp)
        ds_LR = -1 * (ds_UA.t[6, :, :, :] - ds_UA.t[0, :, :, :]) / (ds_UA.gh[6, :, :, :] - ds_UA.gh[0, :, :, :])
        ds_LR.name = 't_lapse_rate'

        ds = xr.merge([ds, ds_LR])

        # Export to netcdf
        nc_file_out = os.path.join(settings['nc_ar_dir'], 'GEM_2_5km_' + settings['hrdps_domain'] + '_' + str(ds.valid_time[0].values) + '.nc')
        print(f'Writing netcdf file {nc_file_out}')
        processed_nc_files.append(nc_file_out)

        ds = ds.rename_dims({'valid_time': 'datetime', 'x':'xgrid_0', 'y':'ygrid_0'})
        ds = ds.rename({'valid_time': 'datetime'}) # also ensure the coordinate gets renamed
        ds = ds.rename_vars({'latitude': 'gridlat_0', 'longitude': 'gridlon_0'})
        ds = ds.rename(settings['hrdps2chm_names'])


        # Convert Uits
        dt_s = 1 * 60 * 60  # seconds (hard coded for now)

        # Air temperature
        ds['t'] = ds.t - 273.15

        # Precipitation rate to accumulation (mm)
        ds['p'] = ds['p'] * dt_s  # density of water cancels out m to mm conversion

        # Pressure
        ds['press'] = ds['press'] / 100.0  # Pa to hPa

        #  Radiation
        # Shortwave radiation incoming
        Qsi_wm2 = ds.Qsi.diff(dim='datetime') / dt_s  # j/m2 to j/(s*m2)

        # Set SW values just below zero to zero
        Qsi_wm2.values[Qsi_wm2.values < 0] = 0

        # First value is unknown (downside of saving as accum...) so we set it to -9999
        # need the transpose to get the coords back into (datetime, y, x)
        ds['Qsi'] = xr.concat([ds.Qsi[0, :, :] * 0 - 9999, Qsi_wm2], dim='datetime').transpose('datetime', 'ygrid_0', 'xgrid_0')

        # Longwave radiation incoming
        Qli_wm2 = ds.Qli.diff(dim='datetime') / dt_s  # j/m2 to j/(s*m2)
        # First value is unknown (downside of saving as accum...) so we set it to -9999
        ds['Qli'] = xr.concat([ds.Qli[0, :, :] * 0 - 9999, Qli_wm2], dim='datetime').transpose('datetime', 'ygrid_0', 'xgrid_0')

        ds.to_netcdf(nc_file_out, engine='netcdf4')

    return True, processed_nc_files
