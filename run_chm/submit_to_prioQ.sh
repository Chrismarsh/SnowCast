#!/bin/bash

#sbatch  --account hpc_c_giws_clark job.sh

#sleep 60
#if  [[ $(squeue -h -A hpc_c_giws_clark -t RUNNING -u cbm038 -n Snowcast) ]]; then
#    echo "Using normal queue submission"
#    while [[ $(squeue -h -A hpc_c_giws_clark -t RUNNING -u cbm038 -n Snowcast) ]]; do
#        sleep 10
#        if ! [[ $(squeue -h -A hpc_c_giws_clark -t RUNNING -u cbm038 -n Snowcast) ]]; then
#            exit 0
#        fi
#    done
#else

#   jobid=$(squeue -h -A hpc_c_giws_clark  -u cbm038 -n Snowcast | tr -s ' ' | awk -F' ' '{print $1}')
#   echo "Cancelling $jobid"
#    scancel $jobid
#fi

#if we get here, then the normal queue didn't work
sbatch --account hpc_c_giws_prio_clark job.sh
#sudo /opt/software/bin/sgiws high_priority on

#give it a minute to service the job
sleep 60
    if ! [[ $(squeue -h -p cnic_giws_high_priority -t RUNNING) ]]; then
        scancel -p cnic_giws_high_priority
 #       sudo /opt/software/bin/sgiws high_priority off
        echo "prio queue failed to run Snowcast"
        exit -1
    fi


while [[ $(squeue -h -p cnic_giws_high_priority) ]]; do
    sleep 10
    if ! [[ $(squeue -h -p cnic_giws_high_priority -t RUNNING) ]]; then
        break
    fi
done

#sudo /opt/software/bin/sgiws high_priority off
