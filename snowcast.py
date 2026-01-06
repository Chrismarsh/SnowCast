# import dask
import importlib
import os

from datetime import datetime
import pickle
from notifier import slack
from met import main as met_main
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
parser.add_argument("-m", "--no-met", required=False, dest='met', action="store_false", help="Update met archive json")
parser.add_argument("-r", "--no-chm", required=False, dest='CHM', action="store_false", help="Run CHM")
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

    step_met = args['met']
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

    # slack.send_slack_notifier(settings['webhook_url'], 'Snowcast run started :zap:', '')


    try:
        try:
            if step_met:
                met_main.update_metdata_json(settings)
        except Exception as e:
            message = 'Snowcast run failed during CHM run :exclamation:\n' + str(e)
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
            if step_postprocess:
                postprocess.main(settings)

        except Exception as e:
            message = 'Snowcast run failed during post processing :exclamation:\n' + str(e)
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
        # slack.send_slack_notifier(settings['webhook_url'], message, '')

        print(message)

        os.remove('.snowcast.lock')
        