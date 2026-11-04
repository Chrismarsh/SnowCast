import subprocess
import shutil
import glob
import os
import time
from contextlib import contextmanager

@contextmanager
def set_cwd(path):
    prev_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)


from collections import defaultdict


def _rolling_copy(filemask, path, archive_dir, ntokeep=3):
    files = sorted(glob.glob(filemask))

    os.makedirs(path, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)

    # Group by variable name (everything before the timestamp)
    groups = defaultdict(list)

    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]

        # snowdepthhavg-0.001x0.001_20260531T230000
        var = stem.rsplit("_", 1)[0]

        groups[var].append(f)

    for var, var_files in groups.items():
        var_files.sort()

        keep = set(var_files[-ntokeep:])

        for f in var_files:
            if f not in keep:
                print(f"Archiving {f}")
                shutil.move(
                    f,
                    os.path.join(archive_dir, os.path.basename(f))
                )

        for f in sorted(keep):
            print(f"Copying {f} for webupload")
            shutil.copy2(f, path)

def upload(settings):

    tiff_path = os.path.join(settings['html_dir'], 'tif')
    asc_path = os.path.join(settings['html_dir'], 'asc')
    #
    # _cleanup_dir(tiff_path)
    # _cleanup_dir(asc_path)
    #
    # for file_type in ['swe_*.asc', 'swe_*.prj']:
    #     _rolling_copy(file_type, asc_path)
    #
    # for file_type in ['swe-0.001x0.002*.tiff', 'swe-0.036x0.036*.tiff']:
    #     _rolling_copy(file_type, tiff_path, 3)

    #
    print('rsyncing outputs...')
    with set_cwd("postprocess/"):
        print(os.getcwd())

        for ext in ["asc", "tiff", "prj"]:
            files = glob.glob(f"*.{ext}")
            for f in files:
                print(f)
                src = os.path.join(os.getcwd(), f)  # your local file
                dst = f"collab-lp:/home/chm003/project/snowcast/{ext}/"

                cmd = f"rsync --progress {src} {dst}"

                result = subprocess.run(cmd, stdin=subprocess.DEVNULL, text=True, capture_output=True, shell=True)

                print(result.stdout)
                # print(result.stderr)
                if result.returncode != 0:
                    print("STDERR:", result.stderr)
                    print("Exit code:", result.returncode)
                    raise Exception(f"rsync failed with exit code {result.returncode}")

    print('Uploading to webhost...')

    retry = 0
    done = False
    current_delay = 30 # sec

    while retry < 10 and not done:
        try:
            # -I to ensure that the quick size/time check is skipped and we always upload the tiles
            # --delete to update remote if we remove files locally
            exec_str = 'rsync -rIt --progress --inplace --force --delete --perms --chmod=0755 %s/ root@www.snowcast.ca:/var/www/html/v2/' % settings['html_dir']
            subprocess.check_call([exec_str], shell=True)
            done = True
        except:
            print("Upload to snowcast failed")
            retry = retry + 1
            time.sleep(current_delay)
            current_delay *= 2

    if not done:
        raise Exception("Failed to upload to Snowcast")

    _rolling_copy(
        "*.tiff",
        path="/home/chm003/project/Snowcast-www/SnowCast/postprocess/tiff/",
        archive_dir="/home/chm003/project/Snowcast-www/SnowCast/postprocess/archive_tiff/",
        ntokeep=3,
    )

    print('done')
