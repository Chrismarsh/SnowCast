#!/bin/bash

jobid=$(sbatch --parsable --account hpc_c_giws_prio_clark "$@")

echo "jobid=$jobid"

#give it a minute to service the job
sleep 2
if ! [[ $(squeue -h -p cnic_giws_high_priority -t RUNNING) ]]; then
  scancel -p cnic_giws_high_priority
  echo "Prio queue failed to run: $@"
  exit 1
fi


while [[ $(squeue -h -p cnic_giws_high_priority) ]]; do
  sleep 10
  if ! [[ $(squeue -h -p cnic_giws_high_priority -t RUNNING) ]]; then
    break
  fi
done

# wait for the job to clear up, otherwise sacct will still show as running even though the above cleared
sleep 5

if [ "$(sacct -X -n -o State --jobs $jobid | xargs)" = "COMPLETED" ];
then
   exit 0 # Success!
fi

echo "Prio queue failed to run: $@"
exit 1
