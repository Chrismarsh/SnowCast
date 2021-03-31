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
    dask.config.set(scheduler=c)

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



    if not os.path.exists(settings['grib_dir']):
        os.mkdir(settings['grib_dir'])

    if not os.path.exists(settings['grib_ar_dir']):
        os.mkdir(settings['grib_ar_dir'])

    if not os.path.exists(settings['nc_ar_dir']):
        os.mkdir(settings['nc_ar_dir'])

    if not os.path.exists(settings['nc_chm_dir']):
        os.mkdir(settings['nc_chm_dir'])

    slack.send_slack_notifier(settings['webhook_url'],'Snowcast run started :zap:','')

    # try:
    #     nwp_main.main(settings)
    # except:
    #     message = 'Snowcast run failed during NWP processing :exclamation:'
    #     slack.send_slack_notifier(settings['webhook_url'], message, '')
    #     raise Exception(message)
    #
    # try:
    #     chm_main.main(settings)
    # except:
    #     message = 'Snowcast run failed during CHM run :exclamation:'
    #     slack.send_slack_notifier(settings['webhook_url'], message, '')
    #     raise Exception(message)
    #
    # try:
    #     plot_main.main(settings)
    # except:
    #     message = 'Snowcast run failed during plot generation :exclamation:'
    #     slack.send_slack_notifier(settings['webhook_url'], message, '')
    #     raise Exception(message)

    try:
        upload.upload(settings)
    except:
        message = 'Snowcast run failed during web upload :exclamation:'
        slack.send_slack_notifier(settings['webhook_url'], message, '')
        raise Exception(message)


    message="Done at =", datetime.now().strftime("%H:%M:%S")
    slack.send_slack_notifier(settings['webhook_url'], message, '')

    print(message)