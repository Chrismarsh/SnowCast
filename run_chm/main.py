import subprocess

def main(settings):
    exec_str = 'mpirun -np 2 %s -f config.json' % settings['chm_bin']
    subprocess.check_call([exec_str], shell=True, cwd='/Users/chris/Documents/science/code/SnowCast/v2/run_chm/')