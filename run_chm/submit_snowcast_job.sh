#!/bin/bash
set -e

 # maximum number of jobs to finish the run
 # 1 year is typically 5 or 6 jobs
 # but we are doing a day so 1 job should be 
 # loads even if we have a bit of a backfill
NUM_JOBS=2
JOB_SUFFIX='SnowCast'



OUTPUT_DIR="output"
CHM_RUN_ARGS=""
echo "OUTPUT_DIR=${OUTPUT_DIR}"
echo "CHM_RUN_ARGS=${CHM_RUN_ARGS}"
JOB_IDS=()
PREVIOUS_JOB_ID=""

# sentinel check
FILE_PATH="${OUTPUT_DIR}/clean_exit"
echo "using $FILE_PATH as sentinel check "


echo $(pwd)

for i in $(seq 1 $NUM_JOBS); do
    JOB_SCRIPT="job${i}_${JOB_SUFFIX}.pbs"
    
    if [ -z "$PREVIOUS_JOB_ID" ]; then
        # No dependency for the first job
        DEPENDENCY=""
    else
        # Set dependency on the previous job
        DEPENDENCY="#PBS -W depend=afterok:$PREVIOUS_JOB_ID"
    fi
    
        JOB_ID="${i}_${JOB_SUFFIX}"


#PBS -l select=50:ncpus=32:mpiprocs=16:mem=185gb

cat << EOF > $JOB_SCRIPT
#!/bin/bash
#PBS -S /bin/bash
#PBS -j oe
#PBS -m abe
#PBS -q development
#PBS -l walltime=01:00:00
#PBS -l select=20:ncpus=80:mpiprocs=40:mem=185gb
#PBS -N job${JOB_ID}
#PBS -o job${JOB_ID}.o
#PBS -e job${JOB_ID}.e
${DEPENDENCY}

# load spack
. ~/project-ords/spack/share/spack/setup-env.sh

# we will use the CHM from the Snowcast spack env
cd /home/chm003/project/Snowcast-www/SnowCast/
spack env activate .

cd /home/chm003/project/Snowcast-www/SnowCast/run_chm

export OMP_NUM_THREADS=1
export UCX_NET_DEVICES=ib0
EOF

# don't do variable expansion for this part as this needs to be run-time during qsub
cat << 'EOF' >> $JOB_SCRIPT
if [ -f "$FILE_PATH" ]; then
    echo "$FILE_PATH file exists. Exiting."
    exit 1
fi
export CHM_WALLCLOCK_LIMIT=$(qstat -f $PBS_JOBID | sed -rn 's/.*Resource_List.walltime = (.*)/\1/p')
EOF

cat << EOF >> $JOB_SCRIPT
mpirun --mca btl_tcp_if_include ib0 -n 800 CHM -f config.json ${CHM_RUN_ARGS}
EOF

        # Submit the job and capture the job ID
        JOB_ID=$(/opt/pbs/bin/qsub $JOB_SCRIPT)

        # Extract the job ID number from the returned string (PBS job ID)
        JOB_ID=$(echo $JOB_ID | cut -d. -f1)
        
        # Set the previous job ID for the next iteration
        PREVIOUS_JOB_ID=$JOB_ID

        JOB_IDS+=("$JOB_ID")

        echo "Submitted job ${i} with ID ${JOB_ID}"
    done

# wait for the bg qsubs to finish before we return
for job in "${JOB_IDS[@]}"; do
    while /opt/pbs/bin/qstat "$job" &>/dev/null; do
      echo "Waiting on $job to finish..."
      sleep 30  # or shorter with a backoff
    done
done

# signal up to Snowcast.py if we have run successfully
# assume failure, checks below change that
RET_CODE=1
# clean up job files
ts=$(date +%F)

dst="run.logs/$ts"
# handle collision if rerun same day
[[ -e "$dst" ]] && dst="${dst}-$(date +%H%M%S)"


PBS_LOGS="$dst/pbs/"
mkdir -p $PBS_LOGS
mv *.o $PBS_LOGS
mv *.pbs $PBS_LOGS

# cache the chm log folder.
CHM_LOGS="$dst/chm"
mkdir -p $CHM_LOGS

if [[ -d log ]]; then
 # clean up logs
  mv log "$CHM_LOGS"

  exceptions_count=$(ag -m1 'std::exception' -- "$CHM_LOGS" | head -n1 | wc -l)
  if (( exceptions_count > 0 )); then
  echo -e "Found std::exception in logs. Checking if fatal..."

    # If this tries to resume from a chkp where we don't have enough met, that's ok
    start_time_failure=$(ag -m1 'Start time is after endtime' -- "$CHM_LOGS" | head -n1 | wc -l)
    if (( start_time_failure > 0 )); then
      echo "Not fatal, met ar is not up to date to resume from chkp"
      RET_CODE=30
    else
      echo "It's fatal"
      RET_CODE=1
    fi
  fi

  exceptions_count=$(ag -m1 'Killed' -- "$CHM_LOGS" | head -n1 | wc -l)
  if (( exceptions_count > 0 )); then
    echo "Found killed in logs. Assuming failure."
    RET_CODE=1
  fi
fi

# this file's presence will override any other checks
if [[ -f "$FILE_PATH" ]]; then
    echo "$FILE_PATH file exists. Assuming success."
    RET_CODE=20
fi

exit $RET_CODE