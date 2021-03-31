import subprocess

def main(settings):
    exec_str = 'mpirun -np 2 /Users/chris/Documents/science/code/SnowCast/v2/run_chm/CHM -f config.json'
    subprocess.check_call([exec_str], shell=True, cwd='/Users/chris/Documents/science/code/SnowCast/v2/run_chm/')