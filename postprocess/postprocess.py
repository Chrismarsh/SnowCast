import dask
import CHM as pc
import time


def main(settings):
    dask.config.set(scheduler='processes')
    dask.config.set(**{'array.slicing.split_large_chunks': True})

    print('Converting model output')

    print('Reading pvd')
    start = time.time()
    df = pc.pvd_to_xarray(settings['chm_outpath'],
                          dxdy=settings['dxdy'],
                          variables=settings['plot_vars'])
    df = df.isel(time=[-48, -1])
    end = time.time()
    print("Took %fs" % (end - start))

    print('Creating 50m TIFFs...')
    start = time.time()
    df.chm.to_raster(crs_out='EPSG:4326')
    end = time.time()
    print("Took %fs" % (end - start) )

    df = df.isel(time=[-48, -1])

    print('Creating 2.5km TIFFs...')
    df_ab = pc.pvd_to_xarray(settings['chm_outpath'],
                          dxdy=2500,
                          variables=['swe'])
    df_ab = df_ab.isel(time=[-48])

    start = time.time()
    df_ab.chm.to_raster(crs_out='EPSG:4326')
    end = time.time()
    print("Took %fs" % (end - start))



    return df