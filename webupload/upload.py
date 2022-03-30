import subprocess
import shutil
import glob
import os


def _rolling_copy(file_type, path):

    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)

    files = glob.glob('swe_*' + file_type)
    files.sort()

    # keep a rolling 7 day archive
    to_keep = files[-7:]

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

    for file_type in ['.asc', '.prj']:
        _rolling_copy(file_type, asc_path)

    _rolling_copy('.tif', tiff_path)


    print('Uploading to webhost...')

    # -I to ensure that the quick size/time check is skipped and we always upload the tiles
    # --delete to update remote if we remove files locally
    exec_str = 'rsync -rIt --force --delete --perms --chmod=0755 %s/ root@www.snowcast.ca:/var/www/html/v2/' % settings['html_dir']
    subprocess.check_call([exec_str], shell=True)

    print('done')
