import glob
import importlib
import os
import shutil
import sys

from nwp_forcing.backfill_hrdps import backfill_grib2
from nwp_forcing.hrdps_grib2_to_nc import hrdps_grib2nc
from nwp_forcing.hrdps_nc_to_chm import hrdps_nc_to_chm


def main(settings):


    # check to see if we need to backfill. This is a bit of a sanity check in case something went super wrong the previous
    # day. This checks if grib_dir already has the files, so won't redownload existing files
    print('Running backfill')
    ret = backfill_grib2(settings)

    # Assume there is a new forecast so convert it
    print('Running grib to nc')
    hrdps_grib2nc(settings)

    for f in glob.glob( os.path.join(settings['grib_dir'], '*.grib2') ):
        shutil.move( f, os.path.join(settings['grib_ar_dir'], os.path.basename(f)) ) #full dst path to ensure overwrite if needed

    for f in glob.glob( os.path.join(settings['grib_dir'], '*.idx') ):
        os.remove(f)

    print('Converting nc to CHM format')
    hrdps_nc_to_chm(settings)
