"""Local/PBS command execution. Persist submissions so interrupted runners cannot duplicate jobs."""
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time
import uuid

from postprocess.cog_store import atomic_json
from .state import RUN_LOCK_FD


class JobFailed(RuntimeError):
    pass


def script_text(command, cwd, result, setup=None):
    # Commands are argv arrays; only a deliberately supplied setup file is shell code.
    temporary = str(result) + '.tmp'
    trap = f'rc=$?; trap - EXIT; printf "%s\\n" "$rc" > {shlex.quote(temporary)}; mv -- {shlex.quote(temporary)} {shlex.quote(str(result))}; exit "$rc"'
    lines = ['#!/bin/bash', 'set -e', f'trap {shlex.quote(trap)} EXIT',
             f'cd -- {shlex.quote(str(cwd))}', 'export OMP_NUM_THREADS=1']
    if setup:
        lines.append(f'source {shlex.quote(str(setup))}')
    # CHM can checkpoint before PBS terminates the allocation.
    lines += ['if [ -n "${PBS_JOBID:-}" ] && [ -n "${SNOWCAST_WALLTIME:-}" ]; then',
              '  export CHM_WALLCLOCK_LIMIT="${SNOWCAST_WALLTIME}"', 'fi', shlex.join(command)]
    return '\n'.join(lines) + '\n'


def wait_pbs(pending_path):
    pending = json.loads(pending_path.read_text())
    if pending['state'] == 'submitting':
        raise RuntimeError(f'PBS submission acknowledgement missing: {pending_path}. '
                           'Inspect the scheduler before recording the job ID or clearing this file.')
    result = Path(pending['result'])
    while not result.exists():
        query = subprocess.run([pending['qstat'], pending['job_id']], capture_output=True, text=True)
        if query.returncode != 0:
            # A scheduler outage, deletion and failure can look the same. Do not
            # equate a failed query with a successful job or submit another job.
            raise RuntimeError(f'PBS job {pending["job_id"]} has no result and cannot be queried; '
                               f'pending state retained in {pending_path}')
        time.sleep(pending['poll_seconds'])
    code = int(result.read_text().strip())
    pending_path.unlink()
    return code


def resume_pending(work):
    for pending in sorted((work / 'jobs').glob('*.pending.json')):
        accepted = json.loads(pending.read_text()).get('accepted_codes', [0])
        code = wait_pbs(pending)
        if code not in accepted:
            raise JobFailed(f'Recovered PBS job failed with exit {code}; inspect {work / "jobs"}')


def execute(command, *, work, cwd, job, label, accepted_codes=(0,)):
    jobs = work / 'jobs'
    jobs.mkdir(exist_ok=True)
    launcher = [part.replace('{ranks}', str(job['ranks'])) for part in job['launcher']]
    command = launcher + [str(part) for part in command]
    for attempt in range(job['attempts']):
        token = f'{label}-{uuid.uuid4().hex[:12]}'
        script, log, result = (jobs / f'{token}{suffix}' for suffix in ('.sh', '.log', '.exit'))
        script.write_text(script_text(command, cwd, result, job['setup']))
        if job['mode'] == 'local':
            with log.open('wb') as output:
                lock_fd = RUN_LOCK_FD.get()
                process = subprocess.Popen(['bash', str(script)], cwd=cwd, stdout=output,
                                           stderr=subprocess.STDOUT, start_new_session=True,
                                           pass_fds=() if lock_fd is None else (lock_fd,))
                try:
                    code = process.wait(timeout=job['timeout_seconds'])
                except BaseException:
                    # Terminate the complete launcher tree, including MPI children.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                    raise
        else:
            pending = jobs / f'{token}.pending.json'
            record = {'state': 'submitting', 'result': str(result), 'qstat': job['qstat'],
                      'poll_seconds': job['poll_seconds'], 'command': command,
                      'accepted_codes': list(accepted_codes)}
            atomic_json(pending, record)
            resources = f'select={job["nodes"]}:ncpus={job["cpus_per_node"]}:mpiprocs={job["ranks_per_node"]}:mem={job["memory"]}'
            submission = subprocess.run([job['qsub'], '-N', f'sc_{label[:10]}', '-q', job['queue'],
                                         '-l', resources, '-l', f'walltime={job["walltime"]}',
                                         '-v', f'SNOWCAST_WALLTIME={job["walltime"]}',
                                         '-o', str(log), '-j', 'oe', str(script)], capture_output=True, text=True)
            if submission.returncode:
                raise JobFailed(f'PBS submission failed; inspect {pending}: {submission.stderr.strip()}')
            job_id = submission.stdout.strip()
            if not job_id or any(c.isspace() for c in job_id):
                raise JobFailed(f'Unexpected PBS acknowledgement; inspect {pending}')
            atomic_json(pending, {**record, 'state': 'submitted', 'job_id': job_id})
            code = wait_pbs(pending)
        if code not in job['retry_codes'] or attempt + 1 == job['attempts']:
            return code, log
        time.sleep(job['retry_delay_seconds'])
    raise AssertionError('Validated attempts must be positive')
