#!/bin/bash
#PBS -S /bin/bash
#PBS -j oe
#PBS -m abe
#PBS -q development
#PBS -l walltime=00:30:00
#PBS -l select=20:ncpus=80:mpiprocs=40:mem=185gb
#PBS -N sc_2tiff

DATE=$(date +%Y%m%dT%H%M%S)
#PBS -o sc_2tiff_${DATE}.o
#PBS -e sc_2tiff_${DATE}.e

. ~/.profile


BASE=/home/chm003/project/Snowcast-www/SnowCast/

# laod snowcast env
cd $BASE
spack env activate .

cd $BASE/postprocess

# double check we had a clean run
#if [[ ! -f "${BASE}/run_chm/output/clean_exit" ]]; then
#    exit 1
#fi


export OMP_NUM_THREADS=1
# export UCX_NET_DEVICES=ib0
FILE_PATH="../run_chm/output/output.nc"
 # --grid  grid_snowcast.nc

#clean up old files.
# Sweep BOTH the top-level postprocess dir (old layout) and the tiff/ subdir
# (chm_ugrid2grid now writes with --tiff-output ./tiff). Use find instead of a
# shell glob so the sweep cannot be silently skipped, and abort the job if the
# move fails.
mkdir -p archive_tiff
mkdir -p archive_asc
find . tiff -maxdepth 1 -name '*.tiff*' -exec mv -t archive_tiff/ {} + || exit 1
find . tiff -maxdepth 1 \( -name '*.asc*' -o -name '*.prj' \) -exec mv -t archive_asc/ {} + || exit 1

# mpirun() {
#   command /fs/site7/eccc/crd/cps/users/chm003/spack/opt/linux-icelake/openmpi-5.0.10-c47f5ygiatexryiy6yy72bsgcke2o6rm/bin/mpirun \
#     --map-by slot \
#     --bind-to core \
#     --hetero-nodes \
#     --runtime-options fwd-environment \
#     --prtemca plm_ssh_args "-o SendEnv=PBS_JOBID" \
#     "$@"
# }

# grab how many times are in this NC file. Use that for the offset to extract
offset=$(ncdump -h $FILE_PATH  | grep currently | grep -Eo '[0-9]+')
# mpirun -n 800 python to_tiff.py $FILE_PATH --dxdy 0.001 --method conservative --timeoffset $((offset - 1)) $((offset - 2))
mpirun -n 800 chm_ugrid2grid $FILE_PATH --dxdy 0.001 --method conservative --timeoffset $((offset - 1)) $((offset - 2)) --tiff-output ./tiff  --variables swe snowdepthavg t


# For AEP
# mpirun  -n 800 python to_tiff.py $FILE_PATH --dxdy 0.01 --method conservative --timeoffset $((offset - 1))
# mpirun --hetero-nodes -n 800 chm_ugrid2grid $FILE_PATH --dxdy 0.01 --method conservative --timeoffset $((offset - 1))  --tiff-output ./tiff