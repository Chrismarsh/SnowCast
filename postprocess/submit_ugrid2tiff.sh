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

# load spack
. ~/project-ords/spack/share/spack/setup-env.sh

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
export UCX_NET_DEVICES=ib0
FILE_PATH="../run_chm/output/output.nc"
 # --grid  grid_snowcast.nc

#clean up old files
mkdir -p archive_tiff
mkdir -p archive_asc
mv  *.tiff* archive_tiff/
mv *.asc* archive_asc/
mv *.prj archive_asc/


# grab how many times are in this NC file. Use that for the offset to extract
offset=$(ncdump -h $FILE_PATH  | grep currently | grep -Eo '[0-9]+')
mpirun --mca btl_tcp_if_include ib0 -n 800 python to_tiff.py $FILE_PATH --dxdy 0.001 --method conservative --timeoffset $((offset - 1)) $((offset - 2))

# For AEP
mpirun --mca btl_tcp_if_include ib0 -n 800 python to_tiff.py $FILE_PATH --dxdy 0.01 --method conservative --timeoffset $((offset - 1))