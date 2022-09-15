# This is the MPI wrapper for the parallel regridding

import CHM as pc
import sys
from mpi4py import MPI


def str2bool(s: str) -> bool:
    if s.lower() == 'true':
        return True

    return False

def main(timestamp: str,
         disconnect: bool,
         weight_002: str,
         weight_036: str,
         save_weights: bool,
         load_weights: bool):

    # if called from SLURM, etc, these cli are coming in as strings
    if isinstance(disconnect, str):
        disconnect = str2bool(disconnect)
        save_weights = str2bool(save_weights)
        load_weights = str2bool(load_weights)

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
