import subprocess

def upload(settings):
    # -I to ensure that the quick size/time check is skipped and we always upload the tiles
    # --delete to update remote if we remove files locally
    exec_str = 'rsync --progress -r -I --delete %s/* root@www.snowcast.ca:/var/www/html/v2/' % settings['html_dir']
    subprocess.check_call([exec_str], shell=True)