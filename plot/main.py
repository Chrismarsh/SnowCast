import dask

from plot.convert_mesh import *
from plot.interactive_map import make_map as make_interactive


import time

def main(settings):
    dask.config.set(scheduler='processes')
    print('Converting model output')

    print('Reading pvd')
    start = time.time()
    df = pc.pvd_to_xarray(settings['chm_outpath'],
                          dxdy=settings['dxdy'],
                          variables = settings['plot_vars'])
    end = time.time()
    print("Took %fs" % (end - start) )

    # df = filter_output(settings)
    # df = df.chunk({'time':-1,'x':-1,'y':-1})
    df = df.isel(time=[-48, -1])

    make_interactive(settings, df)


    print('AB gov output starting')
    df = pc.pvd_to_xarray(settings['chm_outpath'],
                          dxdy=2500,
                          variables=['swe'])
    df = df.isel(time=[-48])

    start = time.time()
    df.chm.to_raster(crs_out='EPSG:4326')
    end = time.time()
    print("Took %fs" % (end - start))
