# import sys
# sys.path.insert(0, "/fs/homeu2/eccc/crd/ords/ccrp/chm003/code/pyCHM/src")

import argparse
import CHM as pc

def main():
    parser = argparse.ArgumentParser(description="Convert UGRID NetCDF to TIFF using CHM.")
    parser.add_argument("input_nc", help="Path to the input .nc file")
    parser.add_argument("--dxdy", type=float, default=0.0001,
                        help="Grid resolution (default: 0.0001)")
    parser.add_argument("--grid", type=str, default=None,
                        help="Grid")
    parser.add_argument("--method", type=str, default="bilinear",
                        choices=["bilinear", "conservative"],
                        help="Interpolation method (default: bilinear)")
    parser.add_argument(
        "--timeoffset",
        type=int,
        nargs="+",             # allows one or more values
        default=None,
        help="Time offset(s) in hours (e.g., --timeoffset 0 6 12 18)",
    )

    args = parser.parse_args()

    pc.ugrid2tiff(args.input_nc, dxdy=args.dxdy, method=args.method,
                  mesh_topology_nc=args.grid, time_offsets=args.timeoffset,
                  variables=['t', 'swe', 'snowdepthavg']
        )

if __name__ == "__main__":
    main()