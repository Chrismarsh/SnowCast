import subprocess
import os

def main(settings):
    exec_str = settings['chm_exec_str']
    subprocess.check_call([exec_str], shell=True, cwd=os.path.join(settings['snowcast_base'],'run_chm'))