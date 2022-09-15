# This is the MPI wrapper for the parallel regridding

import CHM as pc
import sys
from mpi4py import MPI
import os


def main(timestamp, disconnect,
         weight_002='weight_0.002_BILINEAR.nc',
         weight_036='weight_0.036_BILINEAR.nc',
         save_weights=True,
         load_weights=False):

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

    # have been run from the MPI.spawn, so disconnect. But we we came from SLURM, etc dont' do this
    if disconnect:
        comm = MPI.Comm.Get_parent()
        comm.Disconnect()

if __name__ == '__main__':
    main(*sys.argv[1:])
