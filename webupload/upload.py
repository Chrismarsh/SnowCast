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

def _cleanup_dir(path):

    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)

def _rolling_copy(filemask, path, ntokeep=7):
    files = glob.glob(filemask)
    files.sort()

    # keep a rolling 7 day archive
    to_keep = files[-ntokeep:]

    # remove older files
    for f in files:
        if f not in to_keep:
            os.remove(f)

    for file in to_keep:
        print(f'Copying {file} for webupload')
        shutil.copy2(file, path)


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
                dst = f"collab:/home/chm003/project/snowcast/{ext}/"

                cmd = [
                    "rsync", "--progress",
                    src,
                    dst,
                ]

                result = subprocess.run(cmd, stdin=subprocess.DEVNULL, text=True, capture_output=True)

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


    print('done')
