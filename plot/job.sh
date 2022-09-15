#!/bin/bash
#SBATCH --time=01:00:00
#SBATCH --job-name=Snowcast_plotgen
#SBATCH --nodes=12
#SBATCH --tasks-per-node=32
#SBATCH --cpus-per-task=1
#SBATCH --mem=100G

module load gcc/9.3.0
module restore snowcast-prod

source /globalhome/cbm038/HPC/venv/snowcast-prod/bin/activate
cd /globalhome/cbm038/HPC/project/SnowCast/

srun --label --unbuffered python plot/MPI_gdal2tiles.py "$@"