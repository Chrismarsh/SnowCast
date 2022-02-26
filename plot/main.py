# import dask
# from plot.convert_mesh import *
from plot.interactive_map import make_map as make_interactive
import CHM as pc

def main(settings, df):

    if df is None:
        df = pc.pvd_to_xarray(settings['chm_outpath'],
                              dxdy=5000,
                              variables=settings['plot_vars'])
        df = df.isel(time=[-48, -1])
    make_interactive(settings, df)



