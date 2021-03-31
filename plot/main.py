
from plot.convert_mesh import *
from plot.static_map import plot as make_static
from plot.interactive_map import make_map as make_interactive




def main(settings):

    print('Converting model output')
    df = filter_output(settings)
    df = df.compute()
    make_interactive(settings, df)
    # make_interactive(settings, None)

    # make_static(settings, df)
