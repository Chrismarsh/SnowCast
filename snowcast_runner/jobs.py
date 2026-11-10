"""Local/PBS command execution. Persist submissions so interrupted runners cannot duplicate jobs."""
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import time
import uuid

from .cog_store import atomic_json
from .state import RUN_LOCK_FD


class JobFailed(RuntimeError):
    pass


def script_text(command, cwd, result, setup=None, stop_file=None):
    # Commands are argv arrays; only a deliberately supplied setup file is shell code.
    temporary = str(result) + '.tmp'
    trap = f'rc=$?; trap - EXIT; printf "%s\\n" "$rc" > {shlex.quote(temporary)}; mv -- {shlex.quote(temporary)} {shlex.quote(str(result))}; exit "$rc"'
    lines = ['#!/bin/bash', 'set -e', f'trap {shlex.quote(trap)} EXIT']
    if stop_file is not None:
        # A finished chain must not initialize another environment or touch CHM.
        # Nonzero status prevents further afterok dependencies from starting.
        lines.append(f'if [ -f {shlex.quote(str(stop_file))} ]; then exit 99; fi')
    lines += [f'cd -- {shlex.quote(str(cwd))}', 'export OMP_NUM_THREADS=1']
    if setup:
        lines.append(f'source {shlex.quote(str(setup))}')
    # CHM can checkpoint before PBS terminates the allocation.
    lines += ['if [ -n "${PBS_JOBID:-}" ] && [ -n "${SNOWCAST_WALLTIME:-}" ]; then',
              '  export CHM_WALLCLOCK_LIMIT="${SNOWCAST_WALLTIME}"', 'fi', shlex.join(command)]
    return '\n'.join(lines) + '\n'


def wait_pbs(pending_path, *, consume=True):
    pending = json.loads(pending_path.read_text())
    if pending['state'] == 'submitting':
        raise RuntimeError(f'PBS submission acknowledgement missing: {pending_path}. '
                           'Inspect the scheduler before recording the job ID or clearing this file.')
    result = Path(pending['result'])
    while not result.exists():
        query = subprocess.run([pending['qstat'], pending['job_id']], capture_output=True, text=True)
        if query.returncode != 0:
            history = subprocess.run([pending['qstat'], '-xf', pending['job_id']], capture_output=True, text=True)
            state = re.search(r'^\s*job_state\s*=\s*(\w+)\s*$', history.stdout or '', re.MULTILINE)
            status = re.search(r'^\s*Exit_status\s*=\s*(-?\d+)\s*$', history.stdout or '', re.MULTILINE)
            if history.returncode == 0 and state and state[1] == 'F' and status:
                code = int(status[1])
                atomic_json(result.with_suffix('.pbs.json'), {'job_id': pending['job_id'],
                            'job_state': 'F', 'exit_status': code, 'source': 'qstat -xf'})
                if consume:
                    pending_path.unlink()
                return code
            if history.returncode == 0 and state and state[1] in {'Q', 'R', 'H', 'W', 'S', 'T', 'E', 'B'}:
                time.sleep(pending['poll_seconds'])
                continue
            # An unknown job or a scheduler outage is not evidence of completion.
            detail = (history.stderr or query.stderr or '').strip()
            raise RuntimeError(f'PBS job {pending["job_id"]} has no result and cannot be queried; '
                               f'pending state retained in {pending_path}. {detail}')
        time.sleep(pending['poll_seconds'])
    code = int(result.read_text().strip())
    if consume:
        pending_path.unlink()
    return code


def resume_pending(work, *, submit_model_chain=False):
    recovered = []
    for pending in sorted((work / 'jobs').glob('*.pending.json')):
        record = json.loads(pending.read_text())
        if record.get('kind') == 'model-chain':
            from .backfill import resume_chain
            recovered.append(resume_chain(pending, submit_remaining=submit_model_chain))
            continue
        accepted = record.get('accepted_codes', [0])
        code = wait_pbs(pending)
        if code not in accepted:
            raise JobFailed(f'Recovered PBS job failed with exit {code}; inspect {work / "jobs"}')
    return recovered


def submit_pbs(command, *, cwd, job, directory, token, accepted_codes=(0,), dependency=None, stop_file=None):
    """Record submission intent before qsub; retain uncertain acknowledgements."""
    directory.mkdir(exist_ok=True)
    script, log, result, pending = (directory / f'{token}{suffix}'
                                    for suffix in ('.sh', '.log', '.exit', '.pending.json'))
    script.write_text(script_text(command, cwd, result, job['setup'], stop_file))
    record = {'state': 'submitting', 'result': str(result), 'qstat': job['qstat'],
              'poll_seconds': job['poll_seconds'], 'command': command,
              'accepted_codes': list(accepted_codes)}
    atomic_json(pending, record)
    resources = f'select={job["nodes"]}:ncpus={job["cpus_per_node"]}:mpiprocs={job["ranks_per_node"]}:mem={job["memory"]}'
    options = [job['qsub'], '-N', f'sc_{token[:10]}', '-q', job['queue'],
               '-l', resources, '-l', f'walltime={job["walltime"]}',
               '-v', f'SNOWCAST_WALLTIME={job["walltime"]}', '-o', str(log), '-j', 'oe']
    if dependency:
        options += ['-W', f'depend=afterok:{dependency}']
    submission = subprocess.run([*options, str(script)], capture_output=True, text=True)
    if submission.returncode:
        raise JobFailed(f'PBS submission failed; inspect {pending}: {submission.stderr.strip()}')
    job_id = submission.stdout.strip()
    if not job_id or any(c.isspace() for c in job_id):
        raise JobFailed(f'Unexpected PBS acknowledgement; inspect {pending}')
    atomic_json(pending, {**record, 'state': 'submitted', 'job_id': job_id})
    return pending, log


def execute(command, *, work, cwd, job, label, accepted_codes=(0,)):
    jobs = work / 'jobs'
    jobs.mkdir(exist_ok=True)
    launcher = [part.replace('{ranks}', str(job['ranks'])) for part in job['launcher']]
    command = launcher + [str(part) for part in command]
    for attempt in range(job['attempts']):
        token = f'{label}-{uuid.uuid4().hex[:12]}'
        script, log, result = (jobs / f'{token}{suffix}' for suffix in ('.sh', '.log', '.exit'))
        if job['mode'] == 'local':
            script.write_text(script_text(command, cwd, result, job['setup']))
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
            pending, log = submit_pbs(command, cwd=cwd, job=job, directory=jobs, token=token,
                                      accepted_codes=accepted_codes)
            code = wait_pbs(pending)
        if code not in job['retry_codes'] or attempt + 1 == job['attempts']:
            return code, log
        time.sleep(job['retry_delay_seconds'])
    raise AssertionError('Validated attempts must be positive')
