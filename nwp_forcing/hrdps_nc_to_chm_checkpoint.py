
import xarray as xr
import os
import shutil

# reuse this xarray preprocessor to conver the grid -> nc files to a format that CHM will tolerate
from nwp_forcing.hrdps_nc_to_chm import preprocess as preprocess


def hrdps_nc_to_chm_checkpoint(settings, processed_nc_files):
    """
    This converts the the grib 2 nc files into a format CHM can read (just like hrdps_nc_to_chm. However this
    keeps the 1 nc per day. This allows for easier checkpointing usage.
    :param settings: The main settings dict
    :param processed_nc_files: The list of grib -> nc processed files. These are the files that need to be moved and processed
    :return:
    """

    # make sure this exists
    os.makedirs(settings['checkpoint_nc_chm_dir'], exist_ok=True)

    processed_ckpt_nc_files = []
    for file in processed_nc_files:
        ds = xr.open_mfdataset(file,
                               engine='netcdf4',
                               parallel=False,
                               preprocess=lambda x: preprocess(x, settings, keep_forecast=False, keep_all=True)
                               )

        fname = os.path.join( settings['checkpoint_nc_chm_dir'], os.path.basename(file) )
        ds = ds.load()
        ds.to_netcdf(fname,
                     engine='netcdf4',
                     encoding={'datetime': {'dtype': 'int64'}}
                     )
        print(f'Processed hrdps_nc_to_chm_checkpoint for {fname}')
        processed_ckpt_nc_files.append(fname)

    return processed_ckpt_nc_files
