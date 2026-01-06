#!/bin/bash
#PBS -S /bin/bash
#PBS -j oe
#PBS -m abe
#PBS -q development
#PBS -l walltime=01:30:00
#PBS -l select=1:ncpus=80:mpiprocs=80:mem=185gb
#PBS -N sc2_plot
#PBS -o sc2_plot.o
#PBS -e sc2_plot.e

# load spack
. ~/project-ords/spack/share/spack/setup-env.sh

BASE=/home/chm003/project/Snowcast-www/SnowCast/

# laod snowcast env
cd $BASE
spack env activate .

# cd $BASE/plot

export OMP_NUM_THREADS=2
export UCX_NET_DEVICES=ib0

python plot/interactive_map.py