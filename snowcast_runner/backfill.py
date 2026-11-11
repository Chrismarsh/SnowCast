"""PBS-linked CHM segments using one frozen configuration and forcing snapshot."""
import json
import os
from pathlib import Path
import shlex
import sys
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
            submit_pbs(spec['command'],
                       cwd=Path(spec['cwd']), job=spec['job'], directory=directory,
                       token=f'segment-{index + 1:03d}', dependency=previous,
                       stop_file=directory / 'finished.json',
                       command_body=segment_body(spec, directory / 'request.json', index))
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


def segment_body(spec, request, index):
    """Keep MPI in the Bash shell that sourced setup (including shell wrappers).

    Python only checks state before/after CHM; it is never the MPI launcher.
    """
    helper = shlex.join([spec['python'], '-m', 'snowcast_runner.backfill', str(request), str(index)])
    job = spec['job']
    hours, minutes, seconds = map(int, job['walltime'].split(':'))
    budget = hours * 3600 + minutes * 60 + seconds
    lines = [f'{helper} before', 'sc_started=$SECONDS',
             f'for ((sc_attempt=1; sc_attempt<={job["attempts"]}; sc_attempt++)); do',
             f'  sc_remaining=$(({budget} - SECONDS + sc_started))',
             '  if ((sc_remaining < 1)); then sc_remaining=1; fi',
             '  printf -v CHM_WALLCLOCK_LIMIT "%02d:%02d:%02d" "$((sc_remaining / 3600))" '
             '"$((sc_remaining / 60 % 60))" "$((sc_remaining % 60))"',
             '  export CHM_WALLCLOCK_LIMIT', '  set +e',
             '  ' + shlex.join(spec['command']), '  sc_model_rc=$?', '  set -e']
    if job['retry_codes']:
        codes = '|'.join(str(code) for code in job['retry_codes'])
        lines += ['  case "$sc_model_rc" in', f'    {codes})',
                  f'      if ((sc_attempt < {job["attempts"]})); then',
                  f'        sleep {shlex.quote(str(job["retry_delay_seconds"]))}',
                  '        continue', '      fi', '      ;;', '  esac']
    lines += ['  break', 'done', f'{helper} "$sc_model_rc"']
    return '\n'.join(lines)


def check_segment(request, index, code=None):
    """Check progress in short-lived processes on either side of the launch."""
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
        snapshot = _step(directory, index, '.before.json')
        current = {name: list(stat) for name, stat in checkpoint_state(cwd).items()}
        if code is None:
            atomic_json(snapshot, current)
            archive_model_log(Path(spec['work']), cwd)
            return 0
        if code in spec['no_data_codes']:
            outcome = {'state': 'up_to_date'}
        elif code:
            raise JobFailed(f'CHM exit {code}')
        elif (cwd / 'output/clean_exit').is_file():
            outcome = {'state': 'completed'}
        elif current == json.loads(snapshot.read_text()):
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


def run_segment(request, index):
    """Support batch scripts already queued with the original worker command.

    Replace this process with Bash and initialize its shell functions there.
    New submissions already contain segment_body directly in their PBS script.
    """
    from .jobs import script_text

    spec = json.loads(request.read_text())
    script = script_text(spec['command'], Path(spec['cwd']), _step(request.parent, index, '.exit'),
                         spec['job']['setup'], request.parent / 'finished.json',
                         command_body=segment_body(spec, request, index))
    os.execv('/bin/bash', ['bash', '-c', script])


if __name__ == '__main__':
    request, index = Path(sys.argv[1]), int(sys.argv[2])
    if len(sys.argv) == 3:
        run_segment(request, index)
    else:
        raise SystemExit(check_segment(request, index, None if sys.argv[3] == 'before' else int(sys.argv[3])))
