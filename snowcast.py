import dask
import importlib
import os
import sys
from datetime import datetime

from notifier import slack
from nwp_forcing import main as nwp_main
from plot import main as plot_main
from run_chm import main as chm_main
from webupload import upload

if __name__ == '__main__':
    cluster = dask.distributed.LocalCluster(threads_per_worker=1, n_workers=2)
    c = dask.distributed.Client(cluster)
    # dask.config.set(scheduler=c)

    dask.config.set(**{'array.slicing.split_large_chunks': True})

    print("Started at =", datetime.now().strftime("%H:%M:%S"))
    # Load in config file

    # Check user defined configuraiton file
    # Comment from Kevin
    if len(sys.argv) == 1:
        raise ValueError('snowcast.py requires one argument [configuration file] (i.e. python '
                         'snowcast.py forcing_config.py')

    # Get name of configuration file/module
    configfile = sys.argv[-1]

    # Load in configuration file as module
    X = importlib.machinery.SourceFileLoader('config', configfile)
    X = X.load_module()

    # Assing to local variables
    settings = X.settings

    ################################################
    # Internal settings
    # Likely do not need to be changed by the user
    ################################################
    # not currently used
    settings['domain'] = 'west'

    # Define HRDPS variables to download (names match file names in HRDPS system)
    settings['hrdps_variables'] = [
        # temperature at various mb (Kevlin)
        'TMP_ISBL_1015', 'TMP_ISBL_1000', 'TMP_ISBL_0985', 'TMP_ISBL_0970', 'TMP_ISBL_0950', 'TMP_ISBL_0925',
        'TMP_ISBL_0900',

        # Geopotential Height of various mb (geopotential meter)
        'HGT_ISBL_1015', 'HGT_ISBL_1000', 'HGT_ISBL_0985', 'HGT_ISBL_0970', 'HGT_ISBL_0950',
        'HGT_ISBL_0925', 'HGT_ISBL_0900',

        # geopotential of Model surface (geopotential meter)
        'HGT_SFC_0',

        'TMP_TGL_2',  # 2m air temp (kelvin)
        'RH_TGL_2',  # 2m RH

        # Wind speed, direction 10m (m/s)
        'WIND_TGL_10', 'WDIR_TGL_10',

        # Surface pressure  (Pa)
        'PRES_SFC_0',

        # Incoming surface longwave, accumulated flux (J/m^2)
        'DLWRF_SFC_0',

        # Downward incident solar flux (Accumulated), surface, (J/m^2(
        'DSWRF_SFC_0',

        # precipitation rate, surface (kg/m^2/s)
        'PRATE_SFC_0',

        # accumulated precipitation, surface (kg/m^2)
        'APCP_SFC_0'
    ]

    settings['hrdps2chm_names'] = {
        'orog': 'HGT_P0_L1_GST',
        't2m': 't',
        'r2': 'rh',
        'si10': 'u',
        'wdir10': 'vw_dir',
        'sp': 'press',
        'ssrd': 'Qsi',
        'strd': 'Qli',
        'prate': 'p'
    }

    #######################################################

    if not os.path.exists(settings['grib_dir']):
        os.mkdir(settings['grib_dir'])

    if not os.path.exists(settings['grib_ar_dir']):
        os.mkdir(settings['grib_ar_dir'])

    if not os.path.exists(settings['nc_ar_dir']):
        os.mkdir(settings['nc_ar_dir'])

    if not os.path.exists(settings['nc_chm_dir']):
        os.mkdir(settings['nc_chm_dir'])

    slack.send_slack_notifier(settings['webhook_url'],'Snowcast run started :zap:','')

    try:
        nwp_main.main(settings)
    except:
        message = 'Snowcast run failed during NWP processing :exclamation:'
        slack.send_slack_notifier(settings['webhook_url'], message, '')
        raise Exception(message)

    try:
        chm_main.main(settings)
    except:
        message = 'Snowcast run failed during CHM run :exclamation:'
        slack.send_slack_notifier(settings['webhook_url'], message, '')
        raise Exception(message)

    try:
        plot_main.main(settings)
    except:
        message = 'Snowcast run failed during plot generation :exclamation:'
        slack.send_slack_notifier(settings['webhook_url'], message, '')
        raise Exception(message)

    try:
        upload.upload(settings)
    except:
        message = 'Snowcast run failed during web upload :exclamation:'
        slack.send_slack_notifier(settings['webhook_url'], message, '')
        raise Exception(message)


    message = "Finished at " + datetime.now().strftime("%H:%M:%S")
    slack.send_slack_notifier(settings['webhook_url'], message, '')

    print(message)