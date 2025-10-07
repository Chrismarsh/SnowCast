import subprocess
import os
import pandas as pd
import xarray as xr
import numpy as np
import shutil

import json # to pretty print the output
import pyjson5 # to be able to handle comments in json loading
import glob

def main(settings):

    with open(settings['chm_config_path']) as f:
        config = pyjson5.load(f)

    config['output']['ugrid']['variables'] = settings['plot_vars']

    # once we get going from a checkpoint, this will be ignored by the checkpoint loader in CHM
    config['option']['startdate'] = settings['start_date']

    with open(settings['chm_config_path'], 'w') as f:
        js = json.dumps(config, indent=2)
        f.write(js)

    print("Running CHM")
    exec_str = settings['chm_exec_str']
    # exec_str = '%s -f config.json.chkp.json' % os.path.join(settings['snowcast_base'], 'run_chm/CHM')
    subprocess.run(exec_str, check=True, capture_output=True, shell=True,  text=True, cwd=os.path.join(settings['snowcast_base'], 'run_chm'))

    # house keeping on the last run

    # On the last run, we need to use checkpoint frequency=23 to get at the mid-way timestamp to checkpoint
    # but the last timestep will also trigger a checkpoint. However this will be at T00 00 00 which we don't need
    # and we will never resume off this far forward of a forecast. So clean this up
    # chkpt_path = os.path.join(os.path.dirname(settings['chm_outpath']), '..', 'checkpoint',
    #                             f'checkpoint_*T000000*.json')
    # chkpt_path = os.path.abspath(chkpt_path)
    # chkpt_file = glob.glob(chkpt_path)

    # for ckp in chkpt_file:
    #     os.remove(ckp)

    # chkpt_path = os.path.join(os.path.dirname(settings['chm_outpath']), '..', 'checkpoint',
    #                             f'*T000000')
    # chkpt_path = os.path.abspath(chkpt_path)
    # chkpt_file = glob.glob(chkpt_path)

    # for ckp in chkpt_file:
    #     shutil.rmtree(ckp)

    # # update the config file so that it can be immediately used to start the next run
    #     # use 24 here as we want the time the checkpoint will resume off of which is idx23+1
    # midpoint = str(ds.datetime[24].dt.strftime('%Y%m%dT%H%M%S').data)
    # chkpt_path = os.path.join(os.path.dirname(settings['chm_outpath']), '..', 'checkpoint',
    #                             f'checkpoint_{midpoint}*.json')
    # chkpt_path = os.path.abspath(chkpt_path)
    # chkpt_file = glob.glob(chkpt_path)

    # if len(chkpt_file) != 1:
    #     raise Exception(f"Found wrong number of files. {chkpt_file}")

    # config['checkpoint']['load_checkpoint_path'] = chkpt_file[0]


    # with open(settings['chm_config_path'], 'w') as f:
    #     js = json.dumps(config, indent=2)
    #     f.write(js)




