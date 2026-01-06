import shutil
import os
import subprocess
from contextlib import contextmanager
import pickle

@contextmanager
def set_cwd(path):
    prev_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)


def main(settings):

    # clean up the old tile files
    tile_path = os.path.join(settings['html_dir'], 'tiles')
    shutil.rmtree(tile_path, ignore_errors=True)
    os.mkdir(tile_path)

    with set_cwd("plot/"):
        with open('settings.pickle', 'wb') as file:
            pickle.dump(settings, file, protocol=pickle.HIGHEST_PROTOCOL)

    exec_str = "/opt/pbs/bin/qsub -W block=true plot/job.sh"
    print(exec_str)
    subprocess.check_call([exec_str], shell=True, cwd=os.path.join(settings['snowcast_base']))
    #
    # from plot import interactive_map as make_map
    # df = make_map.build_plot_dataframe(settings)
    # make_map.make_map(settings, df)

