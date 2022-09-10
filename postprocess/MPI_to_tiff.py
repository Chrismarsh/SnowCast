# This is the MPI wrapper for the parallel regridding

import CHM as pc
import sys
from mpi4py import MPI

def main(timestamp):
    # this should go in a sbatch job.sh
    # https://www.opendem.info/arc2meters.html
    pc.ugrid2tiff(f'ugrid_{timestamp}.nc',
                  dxdy=0.002,  # ~ 150m
                  method='BILINEAR'
                  )


    print('Creating 2.5km TIFFs...')
    pc.ugrid2tiff(f'ugrid_{timestamp}.nc',
                  dxdy=0.036,  # ~ 2.5km
                  method='BILINEAR'
                  )

    pc.ugrid2tiff(f'ugrid_{timestamp}_diff.nc',
                  dxdy=0.002,  # ~ 150m
                  method='BILINEAR'
                  )

    comm = MPI.Comm.Get_parent()
    comm.Disconnect()

if __name__ == '__main__':
    main(sys.argv[1])
