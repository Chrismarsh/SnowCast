source /globalhome/cbm038/HPC/.bashrc

date
module purge
module load gcc/9.3.0
module load geo-stack/2022c
module load mpi4py/3.1.3 esmf/8.4.0b13 esmpy/8.4.0b13
module save snowcast-prod

source /globalhome/cbm038/HPC/venv/snowcast-prod/bin/activate
cd /globalhome/cbm038/HPC/project/SnowCast

rm -rf run_chm/log

python snowcast.py  -c config_hrdps_west.py "$@"

rm PET*.ESMF_LogFile
