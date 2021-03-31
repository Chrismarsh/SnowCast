import subprocess

def upload(settings):

    exec_str = 'rsync --progress -r %s/* root@www.snowcast.ca:/var/www/html/v2/' % settings['html_dir']
    subprocess.check_call([exec_str], shell=True)