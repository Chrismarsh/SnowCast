import subprocess
import shutil
import glob
import os

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

    _cleanup_dir(tiff_path)
    _cleanup_dir(asc_path)

    for file_type in ['swe_*.asc', 'swe_*.prj']:
        _rolling_copy(file_type, asc_path)

    for file_type in ['swe_150x150*.tif', 'swe_2500x2500*.tif']:
        _rolling_copy(file_type, tiff_path, 3)



    print('Uploading to webhost...')

    # -I to ensure that the quick size/time check is skipped and we always upload the tiles
    # --delete to update remote if we remove files locally
    exec_str = 'rsync -rIt --force --delete --perms --chmod=0755 %s/ root@www.snowcast.ca:/var/www/html/v2/' % settings['html_dir']
    subprocess.check_call([exec_str], shell=True)

    print('done')
