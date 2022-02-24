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

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("-b", "--no-backfill", required=False, dest="backfill", action="store_false", help="(Back)fill met data")
parser.add_argument("-r", "--no-chm", required=False, dest='CHM',action="store_false", help="Run CHM")
parser.add_argument("-p", "--no-plot", required=False, dest='plot', action="store_false", help="Do plot")
parser.add_argument("-u", "--no-upload", required=False, dest='upload', action="store_false", help="Upload")
parser.add_argument("-c", "--config", required=True, default='', type=str,
                help="Config file to use")

if __name__ == '__main__':
    # cluster = dask.distributed.LocalCluster(threads_per_worker=1, n_workers=1)
    # c = dask.distributed.Client(cluster)
    if os.path.exists('.snowcast.lock'):
        print('Snowcast is already running')
        exit(0)
    else:
        open('.snowcast.lock','w')

    args = vars(parser.parse_args())

    step_backfill = args['backfill']
    step_CHM = args['CHM']
    step_plot = args['plot']
    step_upload = args['upload']


    dask.config.set(scheduler='single-threaded')
    dask.config.set(**{'array.slicing.split_large_chunks': True})

    print("Started at =", datetime.now().strftime("%H:%M:%S"))
    # Load in config file


    # Get name of configuration file/module
    configfile = args['config']

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

    slack.send_slack_notifier(settings['webhook_url'], 'Snowcast run started :zap:', '')

    try:
        try:
            if step_backfill:
                nwp_main.main(settings)
        except Exception as e:
            open('.snowcast.lastrun_nwp_error.lock', 'w')

            message = 'Snowcast run failed during NWP processing :exclamation:\ny' + str(e)
            slack.send_slack_notifier(settings['webhook_url'], message, '')

            raise Exception(message)

        try:
            if step_CHM:
                chm_main.main(settings)
        except Exception as e:
            message = 'Snowcast run failed during CHM run :exclamation:\n' + str(e)
            slack.send_slack_notifier(settings['webhook_url'], message, '')
            raise Exception(message)

        try:
            if step_plot:
                plot_main.main(settings)
        except Exception as e:
            message = 'Snowcast run failed during plot generation :exclamation:\n' + str(e)
            slack.send_slack_notifier(settings['webhook_url'], message, '')
            raise Exception(message)

        try:
            if step_upload:
                upload.upload(settings)
        except Exception as e:
            message = 'Snowcast run failed during web upload :exclamation:\n' + str(e)
            slack.send_slack_notifier(settings['webhook_url'], message, '')
            raise Exception(message)
    finally:
        message = "Finished at " + datetime.now().strftime("%H:%M:%S")
        slack.send_slack_notifier(settings['webhook_url'], message, '')

        print(message)

        os.remove('.snowcast.lock')
        