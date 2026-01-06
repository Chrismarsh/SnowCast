#!/bin/bash
#PBS -S /bin/bash
#PBS -j oe
#PBS -m abe
#PBS -q development
#PBS -l walltime=00:30:00
#PBS -l select=1:ncpus=80:mpiprocs=40:mem=185gb
#PBS -N sc_2tiles
#PBS -o sc_2tiles.o
#PBS -e sc_2tiles.e

# load spack
. ~/project-ords/spack/share/spack/setup-env.sh

BASE=/home/chm003/project/Snowcast-www/SnowCast/

# laod snowcast env
cd $BASE
spack env activate .

cd $BASE/plot

export OMP_NUM_THREADS=2
export UCX_NET_DEVICES=ib0

mpirun --mca btl_tcp_if_include ib0 -n 40 python plot/MPI_gdal2tiles.py "$@"