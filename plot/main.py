from plot.interactive_map import make_map as make_interactive
import shutil
import os

def main(settings, df):

    # clean up the old tile files
    tile_path = os.path.join(settings['html_dir'], 'tiles')

    shutil.rmtree(tile_path, ignore_errors=True)

    os.mkdir(tile_path)

    make_interactive(settings, df)
