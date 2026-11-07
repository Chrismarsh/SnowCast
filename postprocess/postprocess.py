import time
import os
from datetime import datetime
from contextlib import contextmanager
from glob import glob
import subprocess
from pathlib import Path

from . import AEP as AEP


@contextmanager
def set_cwd(path):
    prev_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)



def main(settings):

    print('Converting model output')


    print('Creating TIFFs...')
    start = time.time()

    ### CALL PARALLEL MPI REGRIDDING

    # weight_002 = 'weight_0.002_BILINEAR.nc'
    # weight_036 = 'weight_0.036_BILINEAR.nc'
    #
    # load_weights = False
    # save_weights = True
    # if os.path.isfile(weight_002) and os.path.isfile(weight_036):
    #     save_weights = False
    #     load_weights = True


    exec_str = "/opt/pbs/bin/qsub -W block=true postprocess/submit_ugrid2tiff.sh"
    print(exec_str)
    subprocess.check_call([exec_str], 
                          shell=True,
                          cwd=os.path.join(settings['snowcast_base']))

    variables = ['t', 'swe']
    postprocess_dir = os.path.join(settings['snowcast_base'], 'postprocess')

    timestamp_sets = []
    for var in variables:
        pattern = os.path.join(postprocess_dir,'tiff', f'{var}-0.001x0.001_*.tiff')
        timestamps = set()
        for path in glob(pattern):
            filename = os.path.basename(path)
            timestamp = filename.split('_')[-1].split('.')[0]
            try:
                datetime.strptime(timestamp, "%Y%m%dT%H%M%S")
            except ValueError:
                continue
            timestamps.add(timestamp)
        if not timestamps:
            raise RuntimeError(f"No timestamped TIFF files found for variable '{var}' in {postprocess_dir}")
        timestamp_sets.append(timestamps)

    common_timestamps = set.intersection(*timestamp_sets)
    if not common_timestamps:
        vars_list = ', '.join(variables)
        raise RuntimeError(f"No common timestamps across variables {vars_list} in {postprocess_dir}")

    def parse_iso(ts):
        return datetime.strptime(ts, "%Y%m%dT%H%M%S")

    # use the newest timestep. (This used to be min(), which pinned the AEP
    # output to the oldest leftover TIFF once tiff/ stopped being swept.)
    timestamp_ISO = max(common_timestamps, key=parse_iso)
    fixed_time = parse_iso(timestamp_ISO)

    timestamp_AEP = fixed_time.strftime("%Y%m%d%H%M%S")

    # timestamp_AEP = "20251010T230000"
    # timestamp_ISO = "20251010T230000"

    print('Creating AEP outputs...')
    # The AEP outputs for some reason cause ESMF to segfault so this is safeer to downscale with a gdal call
    with set_cwd("postprocess/"):
        for var in variables:
            # requires the _ between var name and time as per
            # https://publicwiki.deltares.nl/spaces/FEWSDOC/pages/8684011/ArcInfoAscii
            AEP.to_ascii(settings, os.path.join(postprocess_dir,'tiff',f'{var}-0.001x0.001_{timestamp_ISO}.tiff'), f'{var}_{timestamp_AEP}.asc')

    if settings.get('webui_enabled', False):
        from .publish_cogs import publish
        publish(
            [Path(postprocess_dir) / 'archive_tiff', Path(postprocess_dir) / 'tiff'],
            Path(settings['webui_data_dir']),
            days=settings.get('webui_keep_days', 10),
            base_url=settings.get('webui_data_url'),
        )




