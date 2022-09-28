#!/bin/bash
#SBATCH --time=01:00:00
#SBATCH --job-name=Snowcast
#SBATCH --nodes=12 
#SBATCH --tasks-per-node=32
#SBATCH --cpus-per-task=1
#SBATCH --mem=150G

# these are controlled from the squeue submit sh script
#SBATCH --account=hpc_c_giws_prio_clark
#ignore.SBATCH --account=hpc_c_giws_clark

#SBATCH --mail-user=chris.marsh@usask.ca
#SBATCH --mail-type=ALL

nt=${SLURM_CPUS_PER_TASK:-1}
export OMP_NUM_THREADS=$nt
module load gcc/9.3.0
#module load chm/1.2.2
srun --label --unbuffered  /globalhome/cbm038/HPC/build-chm-perf-malloc/bin/CHM -f config.json.chkp.json
#srun --label --unbuffered  CHM -f config.json.chkp.json
