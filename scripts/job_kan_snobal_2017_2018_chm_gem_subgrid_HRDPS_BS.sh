#!/bin/bash
#SBATCH --time=12:00:00
#SBATCH --job-name=kan_snobal_2018
#SBATCH --cpus-per-task=32
#SBATCH --ntasks-per-node=1
#SBATCH --nodes=1
#SBATCH --mem=64000M
#SBATCH --account=rpp-hwheater 
#SBATCH --mail-user=vincent.vionnet@usask.ca
#SBATCH --mail-type=ALL


export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

srun ./CHM -f NewBS_NoSubTopo_K0p3_NoCplz0_NoRecirc_WN2500_NoPomLi.json
