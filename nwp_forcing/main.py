import glob
import os
import shutil
import pandas as pd
import pyjson5 # to be able to handle comments in json loading

from nwp_forcing.backfill_hrdps import backfill_grib2
from nwp_forcing.hrdps_grib2_to_nc import hrdps_grib2nc
from nwp_forcing.hrdps_nc_to_chm import hrdps_nc_to_chm
from nwp_forcing.hrdps_nc_to_chm_checkpoint import  hrdps_nc_to_chm_checkpoint
from nwp_forcing import list_dir

def main(settings):


    # check to see if we need to backfill. This is a bit of a sanity check in case something went super wrong the previous
    # day. This checks if grib_dir already has the files, so won't redownload existing files

    print('Running backfill')
    backfill_ret = backfill_grib2(settings)

    # Assume there is a new forecast so convert it
    print('Running grib to nc')
    grib2nc_ret, processed_nc_files = hrdps_grib2nc(settings)

    if not backfill_ret and not grib2nc_ret:
        raise Exception('Backfill requested, however no grib2 files were found to process to nc!')

    # full dst path to ensure overwrite if needed
    for f in glob.glob( os.path.join(settings['grib_dir'], '*.grib2') ):
        shutil.move( f, os.path.join(settings['grib_ar_dir'], os.path.basename(f)) )

    # clean up file locks/tmp files from the grib xr reader
    for f in glob.glob( os.path.join(settings['grib_dir'], '*.idx') ):
        os.remove(f)


    # this checks the end of the complete nc file to know what to back fill
    if settings['create_complete_nc_archive']:
        # build the mega nc file so-as to be able to easily run a full model sim
        print('Converting nc to CHM format')
        _, processed_nc_files = hrdps_nc_to_chm(settings)
    else:
        # we need to check if we have a valid checkpoint resume point in the main CHM config file. If so we can use
        # this to determine what we are missing and only process that
        processed_nc_files = None

        df, start, end = list_dir.list_dir(settings['nc_ar_dir'], settings)

        # check for missing nc files
        diff = pd.date_range(start=start,
                             end=end,
                             freq='1d').difference(df.date)
        if len(diff) > 0:
            missing = '\n'.join([str(d) for d in diff.to_list()])
            raise Exception(f'Missing the following dates:\n {missing}')

        with open(settings['chm_config_path']) as f:
            config = pyjson5.load(f)

        # see if we have a resume from checkpoint we can use to figure out what the last run was
        # anything past this last rur needs to be generated then
        try:
            load_checkpoint_path = config['checkpoint']['load_checkpoint_path']
            with open(load_checkpoint_path) as f:
                chkp_json = pyjson5.load(f)

            end = pd.to_datetime(chkp_json['startdate'], format='%Y%m%dT%H%M%S') - pd.Timedelta('1 hours')
            end = end.strftime('%Y-%m-%d')
            # only keep the input nc to append
            df = df[df.date >= end]
        except:
            print("""Didn't find an existing load_checkpoint_path""")

        if len(df.file.tolist()) > 0:
            processed_nc_files = df.file.tolist()

    if settings['checkpoint_mode']:
        if processed_nc_files is None:
            raise Exception('Checkpoint nc file updates were request but no nc files were marked as new')
        print('Converting nc to CHM checkpoint format')

        # processed_nc_files now will have the chkpt files
        processed_nc_files = hrdps_nc_to_chm_checkpoint(settings, processed_nc_files)

        return processed_nc_files

    return None
