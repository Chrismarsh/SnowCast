#!/bin/bash

sbatch --account hpc_c_giws_prio_clark "$@"

#give it a minute to service the job
sleep 60
if ! [[ $(squeue -h -p cnic_giws_high_priority -t RUNNING) ]]; then
  scancel -p cnic_giws_high_priority
  echo "prio queue failed to run Snowcast"
  exit -1
fi


while [[ $(squeue -h -p cnic_giws_high_priority) ]]; do
  sleep 10
  if ! [[ $(squeue -h -p cnic_giws_high_priority -t RUNNING) ]]; then
    break
  fi
done


