import subprocess
import shutil
import glob
import os


def upload(settings):

    tiff_path = os.path.join(settings['html_dir'], 'asc')
    shutil.rmtree(tiff_path, ignore_errors=True)

    os.makedirs(tiff_path, exist_ok=True)

    # clean up the old files
    files = glob.glob('swe_*.asc')
    files.sort()

    # keep a rolling 7 day archive
    to_keep = files[-7:]

    # remove older files
    for f in files:
        if f not in to_keep:
            os.remove(f)

    for file in glob.glob(r'swe_*.asc'):
        print(f'Copying {file} for webupload')
        shutil.copy2(file, tiff_path)

    print('Uploading to webhost...')

    # -I to ensure that the quick size/time check is skipped and we always upload the tiles
    # --delete to update remote if we remove files locally
    exec_str = 'rsync -raI --force --delete --perms --chmod=0755 %s/* root@www.snowcast.ca:/var/www/html/v2/' % settings['html_dir']
    subprocess.check_call([exec_str], shell=True)

    print('done')
