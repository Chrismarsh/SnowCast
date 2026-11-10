"""PBS-linked CHM segments using one frozen configuration and forcing snapshot."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from .cog_store import atomic_json
from .jobs import JobFailed, submit_pbs, wait_pbs


def _step(directory, index, suffix):
    return directory / f'segment-{index + 1:03d}{suffix}'


def _submit_remaining(spec, directory):
    previous = None
    for index in range(spec['max_runs']):
        if (directory / 'finished.json').exists():
            break
        pending = _step(directory, index, '.pending.json')
        if not pending.exists():
            submit_pbs([spec['python'], '-m', 'snowcast_runner.backfill', str(directory / 'request.json'), str(index)],
                       cwd=Path(spec['cwd']), job=spec['job'], directory=directory,
                       token=f'segment-{index + 1:03d}', dependency=previous,
                       stop_file=directory / 'finished.json')
        record = json.loads(pending.read_text())
        if record['state'] != 'submitted':
            raise RuntimeError(f'PBS submission acknowledgement missing: {pending}. '
                               'Inspect the scheduler before recording the job ID or clearing this file.')
        previous = record['job_id']


def resume_chain(pending, *, submit_remaining=False):
    record = json.loads(pending.read_text())
    directory = Path(record['directory'])
    spec = json.loads((directory / 'request.json').read_text())
    finished = directory / 'finished.json'
    if submit_remaining:
        _submit_remaining(spec, directory)
    for index in range(spec['max_runs']):
        if finished.exists():
            break
        segment = _step(directory, index, '.pending.json')
        if not segment.exists():
            raise RuntimeError(f'Model chain submission was interrupted; rerun snowcast run for this project '
                               f'to submit the remaining segments. Pending state: {pending}')
        code = wait_pbs(segment, consume=False)
        if finished.exists():
            break
        outcome = _step(directory, index, '.outcome.json')
        if code or not outcome.exists() or json.loads(outcome.read_text())['state'] != 'continue':
            atomic_json(finished, {'state': 'failed', 'error': f'CHM segment {index + 1} exited with {code} '
                        f'without a valid continuation result; see {_step(directory, index, ".log")}'})
            break
    if not finished.exists():
        atomic_json(finished, {'state': 'failed', 'error': f'CHM did not finish after {spec["max_runs"]} PBS jobs'})
    outcome = json.loads(finished.read_text())
    # finished.json is permanent. Every queued script checks it before setup,
    # so recovering/preparing a new run cannot restart an old chain's model.
    pending.unlink()
    if outcome['state'] == 'failed':
        raise JobFailed(outcome['error'])
    return outcome['state']


def run_chain(project, config):
    checkpoint = json.loads(config.read_text()).get('checkpoint', {})
    if project.model['max_runs'] > 1 and not all(checkpoint.get(key) is True
                                               for key in ('save_checkpoint', 'auto_resume', 'on_wallclock_limit')):
        raise ValueError('PBS backfills require checkpoint.save_checkpoint, auto_resume and on_wallclock_limit '
                         'to be true in the CHM configuration')
    jobs = project.work / 'jobs'
    jobs.mkdir(exist_ok=True)
    token = f'{project.id}-chm-chain-{uuid.uuid4().hex[:12]}'
    directory = jobs / token
    directory.mkdir()
    job = json.loads(json.dumps(project.model['job'], default=str))
    command = [part.replace('{ranks}', str(job['ranks'])) for part in job['launcher']]
    command += [part.replace('{config}', str(config)) for part in project.model['command']]
    spec = {'cwd': str(config.parent), 'work': str(project.work), 'job': job, 'command': command,
            'python': sys.executable, 'max_runs': project.model['max_runs'],
            'no_data_codes': project.model['no_data_codes']}
    atomic_json(directory / 'request.json', spec)
    pending = jobs / f'{token}.pending.json'
    atomic_json(pending, {'kind': 'model-chain', 'directory': str(directory)})
    return resume_chain(pending, submit_remaining=True)


def run_segment(request, index):
    """Runs on one PBS allocation, independently of the launching CLI process."""
    from .model import checkpoint_state, archive_model_log

    spec = json.loads(request.read_text())
    directory = request.parent
    finished = directory / 'finished.json'
    if finished.exists():
        return 99
    cwd = Path(spec['cwd'])
    try:
        if not 0 <= index < spec['max_runs']:
            raise ValueError('Invalid CHM segment number')
        if index:
            previous = json.loads(_step(directory, index - 1, '.outcome.json').read_text())
            if previous['state'] != 'continue':
                raise RuntimeError('Previous CHM segment did not authorize continuation')
        before = checkpoint_state(cwd)
        archive_model_log(Path(spec['work']), cwd)
        job = spec['job']
        started = time.monotonic()
        hours, minutes, seconds = map(int, job['walltime'].split(':'))
        budget = hours * 3600 + minutes * 60 + seconds
        for attempt in range(job['attempts']):
            remaining = max(1, budget - int(time.monotonic() - started))
            environment = {**os.environ, 'CHM_WALLCLOCK_LIMIT':
                           f'{remaining // 3600:02d}:{remaining // 60 % 60:02d}:{remaining % 60:02d}'}
            code = subprocess.run(spec['command'], cwd=cwd, env=environment).returncode
            if code not in job['retry_codes'] or attempt + 1 == job['attempts']:
                break
            time.sleep(job['retry_delay_seconds'])
        if code in spec['no_data_codes']:
            outcome = {'state': 'up_to_date'}
        elif code:
            raise JobFailed(f'CHM exit {code}')
        elif (cwd / 'output/clean_exit').is_file():
            outcome = {'state': 'completed'}
        elif checkpoint_state(cwd) == before:
            raise JobFailed('CHM exited without clean_exit or a new checkpoint')
        elif index + 1 == spec['max_runs']:
            raise JobFailed(f'CHM did not finish after {spec["max_runs"]} PBS jobs; checkpoints retained')
        else:
            outcome = {'state': 'continue'}
    except Exception as error:
        outcome = {'state': 'failed', 'error': f'CHM segment {index + 1}: {error}; '
                   f'see {_step(directory, index, ".log")}'}
    atomic_json(_step(directory, index, '.outcome.json'), outcome)
    if outcome['state'] != 'continue':
        atomic_json(finished, outcome)
    return 1 if outcome['state'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(run_segment(Path(sys.argv[1]), int(sys.argv[2])))
