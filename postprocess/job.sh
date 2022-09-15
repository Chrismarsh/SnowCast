#!/bin/bash
#SBATCH --time=01:00:00
#SBATCH --job-name=Snowcast_postprocess
#SBATCH --nodes=12
#SBATCH --tasks-per-node=32
#SBATCH --cpus-per-task=1
#SBATCH --mem=100G

nt=${SLURM_CPUS_PER_TASK:-1}
export OMP_NUM_THREADS=$nt
module load gcc/9.3.0
module restore snowcast-prod

source /globalhome/cbm038/HPC/venv/snowcast-prod/bin/activate
cd /globalhome/cbm038/HPC/project/SnowCast/

srun --label python postprocess/MPI_to_tiff.py "$@"