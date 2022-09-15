import CHM as pc
import time
import pandas as pd
import subprocess
import sys
import os
import xarray as xr
import  itertools

from . import AEP as AEP


from mpi4py import MPI

def main(settings):

    print('Converting model output')

    print('Reading pvd')

    df = pc.open_pvd(settings['chm_outpath'])
    df = df.iloc[[0, -1]] #start of forecast and the future

    print('Creating ugrid...')
    start = time.time()

    timestamp = df.iloc[[0]].datetime[0].strftime('%Y%m%d%H%M')
    timestamp_ISO = df.iloc[[0]].datetime[0].strftime('%Y%m%dT%H%M%S') # need the ISO time to match ugrid2tiff

    # build up a meta data dataframe to return to use in the map generation.


    ugrid_fname = f'ugrid_{timestamp}.nc'
    ugrid_diff_fname = ugrid_fname[:-3] + '_diff.nc'

    if os.path.isfile(ugrid_fname):
        os.remove(ugrid_fname)

    if os.path.isfile(ugrid_diff_fname):
        os.remove(ugrid_diff_fname)

    pc.vtu_to_ugrid(df,
                    ugrid_fname,
                    settings['plot_vars'])

    # creates the difference ugrid for today
    xr.set_options(keep_attrs=True) # don't mangle the attrs that are critical for ugrid to work
    ds = xr.open_mfdataset(ugrid_fname)



    diff = ds.isel(time=0) - ds.isel(time=-1)

    # the subsctraion will have mangled these so reset them
    diff['Mesh2_face_nodes'] = ds['Mesh2_face_nodes']
    diff['Mesh2_node_x'] = ds['Mesh2_node_x']
    diff['Mesh2_node_y'] = ds['Mesh2_node_y']
    diff['global_id'] = ds['global_id']

    ugridvars = set(ds.data_vars) - set(
        ['Mesh2', 'Mesh2_face_nodes', 'Mesh2_node_x', 'Mesh2_node_y', 'Mesh2_face_x', 'Mesh2_face_y', 'time',
         'global_id'])

    # add back a time coord+dim
    diff = diff.assign_coords(time=("time", [ds.time[0].data]))

    rename_dic = {}
    for v in ugridvars:
        diff[v] = diff[v].expand_dims('time')

        rename_dic[v] = f'{v}_diff'

    diff = diff.rename_vars(rename_dic)

    diff.to_netcdf(ugrid_diff_fname,
                   encoding={'time': {'dtype': 'int32'}} #required otherwise it writes as int64 which ESMF can't handle
                   )
    diff.close()
    diff = None

    # holds information about what was done during the post processing step
    dt = df['datetime'].dt.strftime('%Y%m%dT%H%M%S')

    ugridvars = list(ugridvars)

    product = [x for x in itertools.product(ugridvars, dt)]

    # diffs are only valid as named by the starting ts, so we need a seperate list for their product
    product.extend([x for x in itertools.product([f'{v}_diff' for v in ugridvars], [dt[0]])])

    df = pd.DataFrame(product, columns=['var', 'datetime'])

    df['time'] = pd.to_datetime(df.datetime)
    df['dxdy'] = settings['dxdy'] # TODO: doesn't actually control anything in the regridding step!
    #used in the plot centering step
    df['lon'] = ds.Mesh2_node_x.mean().values
    df['lat'] = ds.Mesh2_node_y.mean().values
    # build up the list of tiffs we processed
    df['tiff'] = df.apply(lambda row: f"""{row['var']}-{row['dxdy']}x{row['dxdy']}_{row['datetime']}.tiff""", axis=1)
    df = df.set_index(['var', 'time'])
    df = df.sort_index(axis=1)

    ds.close()
    ds = None


    end = time.time()
    print("Took %fs" % (end - start))


    print('Creating TIFFs...')
    start = time.time()

    ### CALL PARALLEL MPI REGRIDDING

    weight_002 = 'weight_0.002_BILINEAR.nc'
    weight_036 = 'weight_0.036_BILINEAR.nc'

    load_weights = False
    save_weights = True
    if os.path.isfile(weight_002) and os.path.isfile(weight_036):
        save_weights = False
        load_weights = True


    if 'postprocess_exec_str' in settings:
        exec_str = """f{settings['postprocess_exec_str']} {timestamp} {True} {weight_002} {weight_036} {save_weights} {load_weights}"""
        subprocess.check_call([exec_str], shell=True, cwd=os.path.join(settings['snowcast_base'], 'postprocess]'))
    else:
        comm = MPI.COMM_SELF.Spawn(sys.executable,
                                   args=[os.path.join('postprocess', 'MPI_to_tiff.py'),
                                         timestamp, True, weight_002, weight_036,save_weights, load_weights ],
                                   maxprocs=settings['postprocess_maxprocs'])

        comm.Disconnect()
    end = time.time()
    print("Took %fs" % (end - start))

    # Make the ~2.5km asc raster for AEP
    todays_tiff = f't-0.036x0.036_{timestamp_ISO}.tiff'
    todays_asc = f'swe_{timestamp}.asc'
    AEP.to_ascii(settings, f'{todays_tiff}', todays_asc)

    return df
