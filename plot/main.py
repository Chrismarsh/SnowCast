import dask

from plot.convert_mesh import *
from plot.interactive_map import make_map as make_interactive
from plot.static_map import plot as make_static


def main(settings):
    dask.config.set(scheduler='processes')
    print('Converting model output')
    df = filter_output(settings)
    # df = df.chunk({'time':-1,'x':-1,'y':-1})
    make_interactive(settings, df)


    # make_static(settings, df)
