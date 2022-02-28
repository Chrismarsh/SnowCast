import subprocess
import shutil
import glob
import os

def upload(settings):

    tiff_path = os.path.join(settings['html_dir'],'tiff')
    shutil.rmtree(tiff_path, ignore_errors = True)

    os.makedirs(tiff_path, exist_ok=True)

    for file in glob.glob(r'*2500x2500*.tif'):
        print(f'Copying {file} for webupload')
        shutil.copy2(file, tiff_path)

    print('Uploading to webhost...', end='')

    # -I to ensure that the quick size/time check is skipped and we always upload the tiles
    # --delete to update remote if we remove files locally
    exec_str = 'rsync -r -I --delete --perms --chmod=D07550,F0755 %s/* root@www.snowcast.ca:/var/www/html/v2/' % settings['html_dir']
    subprocess.check_call([exec_str], shell=True)

    print('done')