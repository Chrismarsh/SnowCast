# wraps the gdal2tiles call

import sys
from typing import List
from mpi4py import MPI
from osgeo_utils.gdal2tiles import main as gdal2tiles

def main(argv: List[str] = sys.argv):
    disconnect = True
    if argv[-1] == 'False':
        disconnect = False
    gdal2tiles(argv if disconnect else argv[:-1])

    if disconnect:
        comm = MPI.Comm.Get_parent()
        comm.Disconnect()


if __name__ == '__main__':
    main(sys.argv)