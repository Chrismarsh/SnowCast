from plot.interactive_map import make_map as make_interactive
from pathlib import Path
import os


def main(settings, df):

    # clean up the old tile files
    tile_path = os.path.join(settings['html_dir'], 'tiles')

    Path(tile_path).unlink(missing_ok=True)
    os.mkdir(tile_path)

    make_interactive(settings, df)
