import subprocess
import os
import pandas as pd
import xarray as xr
import numpy as np
import shutil

import json # to pretty print the output
import pyjson5 # to be able to handle comments in json loading
import glob

def main(settings, processed_nc_files):

    with open(settings['chm_config_path']) as f:
        config = pyjson5.load(f)

    config['output']['mesh']['variables'] = settings['plot_vars']

    with open(settings['chm_config_path'], 'w') as f:
        js = json.dumps(config, indent=2)
        f.write(js)

    # if we are not checkpoint proceed as before
    if not settings['checkpoint_mode']:
        exec_str = settings['chm_exec_str']
        subprocess.check_call([exec_str], shell=True, cwd=os.path.join(settings['snowcast_base'], 'run_chm'))
        return

    # checkpoint, so now need to deal with this run

    with open(settings['chm_config_path']) as f:
        config = pyjson5.load(f)

    # ensure there is a checkpoint section
    if not 'checkpoint' in config.keys():
        config['checkpoint'] = {}

    config['checkpoint']['save_checkpoint'] = True

    load_checkpoint_path = None
    try:
        load_checkpoint_path = config['checkpoint']['load_checkpoint_path']
    except:
        # we don't have a file to read from, so /assume/ that this is the start of a checkpointing model run
        print('No existing load_checkpoint_path found, enabling checkpointing')

    i = 1

    # this will be almost certainly 1 iteration but it might not be if we had some backfill
    # note: These files are naemd as if they start at 00, but they actually start at 01 so that valid data is present!
    for nc in processed_nc_files:

        last = True if i == len(processed_nc_files) else False

        # each file has 48 timesteps. If we have multiple files,
        # we have to run through each one 50%, checkpoint, and then start the next

        config['forcing']['file'] = nc

        ds = xr.open_mfdataset(nc)

        # if a chkppoint is set to resume it'll over write this
        # otherwise, ensure we start from hour = 1 as 00 has invalid data
        start = str(ds.datetime[0].dt.strftime('%Y%m%dT%H%M%S').data)
        config['option']['startdate'] = start

        # either just run half the netcdf file or if we are the last run the whole thing as that will incl the forecast
        end_idx = 23 if not last else 46

        end = str(ds.datetime[end_idx].dt.strftime('%Y%m%dT%H%M%S').data)
        config['option']['enddate'] = end

        config['checkpoint']['on_last'] = True
        config['checkpoint'].pop('frequency', None) #

        # we only want to do this on the last run as it can overwrite existing chkpts
        if last:
            config['checkpoint']['frequency'] = 23
            config['checkpoint']['on_last'] = False



        print(f'To process file i={i}, {nc}')
        print(f'\tstart={start}')
        print(f'\tend={end}')
        print(f'\tindexes=0,{end_idx}')

        # first ts
        if i == 1:
            # we have a specified checkpoint
            if load_checkpoint_path is not None:
                print(f'\tresuming from {load_checkpoint_path}')
            else:
                print(f'\tno chkpoint resume specified')
        else:
            # resume from the chkpoint created at the end of the last run
            chkpt_path = os.path.join(os.path.dirname(settings['chm_outpath']), '..', 'checkpoint', f'checkpoint_{start}.np*.json')
            chkpt_path = os.path.abspath(chkpt_path)

            chkpt_file = glob.glob(chkpt_path)
            if len(chkpt_file) == 0:
                raise Exception(f"Expected to find a checkpoint file but did not. Looked for {chkpt_path}")
            elif len(chkpt_file) > 1:
                raise Exception(f"Expected to find a checkpoint file but found multiple. Got: {chkpt_file}")
            chkpt_file = chkpt_file[0]
            config['checkpoint']['load_checkpoint_path'] = chkpt_file
            print(f'\tload_checkpoint_path={chkpt_file}')


        with open(settings['chm_config_path'] + '.chkp.json', 'w') as f:
            js = json.dumps(config, indent=2)
            f.write(js)

        # exec_str = settings['chm_exec_str']
        exec_str = '%s -f config.json.chkp.json' % os.path.join(settings['snowcast_base'], 'run_chm/CHM')
        # print(subprocess.run(exec_str, check=True, capture_output=True, shell=True,  text=True, cwd=os.path.join(settings['snowcast_base'], 'run_chm')).stdout)

        # house keeping on the last run
        if last:
            # On the last run, we need to use checkpoint frequency=23 to get at the mid-way timestamp to checkpoint
            # but the last timestep will also trigger a checkpoint. However this will be at T00 00 00 which we don't need
            # and we will never resume off this far forward of a forecast. So clean this up
            chkpt_path = os.path.join(os.path.dirname(settings['chm_outpath']), '..', 'checkpoint',
                                      f'checkpoint_*T000000*.json')
            chkpt_path = os.path.abspath(chkpt_path)
            chkpt_file = glob.glob(chkpt_path)

            for ckp in chkpt_file:
                os.remove(ckp)

            chkpt_path = os.path.join(os.path.dirname(settings['chm_outpath']), '..', 'checkpoint',
                                      f'*T000000')
            chkpt_path = os.path.abspath(chkpt_path)
            chkpt_file = glob.glob(chkpt_path)

            for ckp in chkpt_file:
                shutil.rmtree(ckp)

            # update the config file so that it can be immediately used to start the next run
                # use 24 here as we want the time the checkpoint will resume off of which is idx23+1
            midpoint = str(ds.datetime[24].dt.strftime('%Y%m%dT%H%M%S').data)
            chkpt_path = os.path.join(os.path.dirname(settings['chm_outpath']), '..', 'checkpoint',
                                      f'checkpoint_{midpoint}*.json')
            chkpt_path = os.path.abspath(chkpt_path)
            chkpt_file = glob.glob(chkpt_path)

            if len(chkpt_file) != 1:
                raise Exception(f"Found wrong number of files. {chkpt_file}")

            config['checkpoint']['load_checkpoint_path'] = chkpt_file[0]


            with open(settings['chm_config_path'], 'w') as f:
                js = json.dumps(config, indent=2)
                f.write(js)

        i = i+1


