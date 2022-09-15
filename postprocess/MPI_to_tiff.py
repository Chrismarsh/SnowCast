# This is the MPI wrapper for the parallel regridding

import CHM as pc
import sys
from mpi4py import MPI
import os


def main(timestamp):

    weight_002 = 'weight_0.002_BILINEAR.nc'
    weight_036 = 'weight_0.036_BILINEAR.nc'

    load_weights = False
    save_weights = True
    if os.path.isfile(weight_002) and os.path.isfile(weight_036):
        save_weights = False
        load_weights = True

    # this should go in a sbatch job.sh
    # https://www.opendem.info/arc2meters.html
    pc.ugrid2tiff(f'ugrid_{timestamp}.nc',
                  dxdy=0.002,  # ~ 150m
                  method='BILINEAR',
                  save_weights_file=weight_002 if save_weights else None,
                  load_weights_file=weight_002 if load_weights else None
                  )


    print('Creating 2.5km TIFFs...')
    pc.ugrid2tiff(f'ugrid_{timestamp}.nc',
                  dxdy=0.036,  # ~ 2.5km
                  method='BILINEAR',
                  save_weights_file=weight_036 if save_weights else None,
                  load_weights_file=weight_036 if load_weights else None
                  )

    pc.ugrid2tiff(f'ugrid_{timestamp}_diff.nc',
                  dxdy=0.002,  # ~ 150m
                  method='BILINEAR',
                  save_weights_file=weight_002 if save_weights else None,
                  load_weights_file=weight_002 if load_weights else None
                  )

    comm = MPI.Comm.Get_parent()
    comm.Disconnect()

if __name__ == '__main__':
    main(sys.argv[1])
