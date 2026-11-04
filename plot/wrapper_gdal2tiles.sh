#!/bin/bash

. ~/.profile
mpirun -n 75 gdal2tiles "$@"