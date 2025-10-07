# import dask
import importlib
import os

from datetime import datetime
import pickle
from notifier import slack
from nwp_forcing import main as nwp_main
from plot import main as plot_main
from run_chm import main as chm_main
from webupload import upload
from postprocess import postprocess
from pathlib import Path

import dask
dask.config.set(**{'array.slicing.split_large_chunks': False})
dask.config.set(scheduler='single-threaded')

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("-r", "--no-chm", required=False, dest='CHM',action="store_false", help="Run CHM")
parser.add_argument("-p", "--no-plot", required=False, dest='plot', action="store_false", help="Do plot")
parser.add_argument("-a", "--no-postprocess", required=False, dest='postprocess', action="store_false", help="Post process CHM->TIFF")
parser.add_argument("-u", "--no-upload", required=False, dest='upload', action="store_false", help="Upload")
parser.add_argument("-c", "--config", required=True, default='', type=str,
                help="Config file to use")

if __name__ == '__main__':

    args = vars(parser.parse_args())

    if os.path.exists('.snowcast.lock'):
        print('Snowcast is already running')
        exit(0)
    else:
        open('.snowcast.lock','w')

    step_CHM = args['CHM']
    step_plot = args['plot']
    step_upload = args['upload']
    step_postprocess = args['postprocess']

    print("Started at =", datetime.now().strftime("%H:%M:%S"))

    # Get name of configuration file/module
    configfile = args['config']

    # Load in configuration file as module
    X = importlib.machinery.SourceFileLoader('config', configfile)
    X = X.load_module()

    # Assing to local variables
    settings = X.settings


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

    #if we are running in checkpoint mode, this will hold the list of today's (but maybe >1 day!) set of processed
    # nc files
    processed_nc_files = None

    try:
        try:
            if step_CHM:
                chm_main.main(settings, processed_nc_files)
        except Exception as e:
            message = 'Snowcast run failed during CHM run :exclamation:\n' + str(e)
            slack.send_slack_notifier(settings['webhook_url'], message, '')
            raise Exception(message)

#TODO: Replace this with just time offsets
        df = None
        try:
            if step_postprocess:

                # clean up old files
                Path('postprocess_df').unlink(missing_ok=True)
                df = postprocess.main(settings)

                with open('postprocess_df', 'wb') as f:
                    pickle.dump(df, f)

        except Exception as e:
            message = 'Snowcast run failed during post processing :exclamation:\n' + str(e)
            slack.send_slack_notifier(settings['webhook_url'], message, '')

            raise Exception(message)

        try:
            if step_plot:
                if not step_postprocess:
                    try:
                        with open('postprocess_df', 'rb') as f:
                            df = pickle.load(f)
                    except FileNotFoundError as e:
                        raise Exception("Last postprocess did not run correctly. Please rerun postprocess.")

                plot_main.main(settings, df)
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
        