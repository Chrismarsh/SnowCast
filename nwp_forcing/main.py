import glob
import importlib
import os
import shutil
import sys

from nwp_forcing.backfill_hrdps import backfill_grib2
from nwp_forcing.hrdps_grib2_to_nc import hrdps_grib2nc
from nwp_forcing.hrdps_nc_to_chm import hrdps_nc_to_chm
from nwp_forcing.hrdps_nc_to_chm_checkpoint import  hrdps_nc_to_chm_checkpoint


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

    if settings['create_complete_nc_archive']:
        # even in chechk point mode still build the mega nc file so-as to be able to easily run a full model sim
        print('Converting nc to CHM format')
        _, processed_nc_files = hrdps_nc_to_chm(settings)

    if settings['checkpoint_mode']:
        if processed_nc_files is None:
            raise Exception('Checkpoint nc file updates were request but no nc files were marked as new')
        print('Converting nc to CHM checkpoint format')

        # processed_nc_files now will have the chkpt files
        processed_nc_files = hrdps_nc_to_chm_checkpoint(settings, processed_nc_files)

        return processed_nc_files

    return None
