#!/bin/bash

jobib=$(sbatch --parsable --account hpc_c_giws_prio_clark "$@")

#give it a minute to service the job
sleep 5
if ! [[ $(squeue -h -p cnic_giws_high_priority -t RUNNING) ]]; then
  scancel -p cnic_giws_high_priority
  echo "prio queue failed to run Snowcast"
  exit 1
fi


while [[ $(squeue -h -p cnic_giws_high_priority) ]]; do
  sleep 10
  if ! [[ $(squeue -h -p cnic_giws_high_priority -t RUNNING) ]]; then
    break
  fi
done

# xargs trims whitespace
if [ "$(sacct -X -n -o State --jobs ${jobid} | xargs)" = "COMPLETED" ];
then
   return 0 # Success!
fi

return 1
