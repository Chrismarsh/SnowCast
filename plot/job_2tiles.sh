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

. ~/.profile

BASE=/home/chm003/project/Snowcast-www/SnowCast/

# laod snowcast env
cd $BASE
spack env activate .

cd $BASE/plot

export OMP_NUM_THREADS=2
# export UCX_NET_DEVICES=ib0

# mpirun() {
#   command /fs/site7/eccc/crd/cps/users/chm003/spack/opt/linux-icelake/openmpi-5.0.10-c47f5ygiatexryiy6yy72bsgcke2o6rm/bin/mpirun \
#     --map-by slot \
#     --bind-to core \
#     --hetero-nodes \
#     --runtime-options fwd-environment \
#     --prtemca plm_ssh_args "-o SendEnv=PBS_JOBID" \
#     "$@"
# }
#--mca btl_tcp_if_include ib0 
mpirun -n 40 python plot/MPI_gdal2tiles.py "$@"