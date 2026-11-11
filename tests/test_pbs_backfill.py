"""Exercise real generated batch scripts with a small dependency-aware scheduler."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from snowcast_runner.cli import main
from snowcast_runner.project import load_project
from test_project_runner import project_file, change


class Scheduler:
    def __init__(self, monkeypatch):
        self.real_run = subprocess.run
        self.jobs = {}
        self.submissions = []
        self.disconnect = False
        self.lose_exit = set()
        self.history_calls = []
        monkeypatch.setattr(subprocess, 'run', self.run)

    def start(self, job_id):
        job = self.jobs[job_id]
        if 'code' in job:
            return
        dependency = job['dependency']
        if dependency:
            self.start(dependency)
            if self.jobs[dependency]['code']:
                job['code'] = 271  # PBS removes an unsatisfied afterok dependency.
                return
        result = self.real_run(['bash', str(job['script'])], capture_output=True, text=True,
                               env={**os.environ, 'PBS_JOBID': job_id, 'SNOWCAST_WALLTIME': '06:00:00'})
        job['log'].write_text(result.stdout + result.stderr)
        job['code'] = result.returncode
        if job_id in self.lose_exit:
            job['script'].with_suffix('.exit').unlink(missing_ok=True)

    def run(self, command, **kwargs):
        if command[0] == 'qsub':
            job_id = f'{len(self.jobs) + 1}.server'
            dependency = command[command.index('-W') + 1].removeprefix('depend=afterok:') if '-W' in command else None
            assert 'walltime=06:00:00' in command
            assert 'SNOWCAST_WALLTIME=06:00:00' in command
            self.jobs[job_id] = {'script': Path(command[-1]), 'log': Path(command[command.index('-o') + 1]),
                                 'dependency': dependency}
            self.submissions.append(command)
            return subprocess.CompletedProcess(command, 0, job_id + '\n', '')
        if command[0] == 'qstat':
            if self.disconnect:
                raise OSError('launching process disconnected')
            job_id = command[-1]
            self.start(job_id)
            if '-xf' in command:
                self.history_calls.append(job_id)
                return subprocess.CompletedProcess(command, 0,
                    f'Job Id: {job_id}\n    job_state = F\n    Exit_status = {self.jobs[job_id]["code"]}\n', '')
            return subprocess.CompletedProcess(command, 153, '', 'Unknown Job Id')
        return self.real_run(command, **kwargs)


@pytest.fixture
def pbs_project(project_file):
    model = project_file.parent / 'backfill_model.py'
    model.write_text('''import json, os
from pathlib import Path
assert os.environ['CHM_WALLCLOCK_LIMIT'].startswith('06:')
count = Path('runs')
n = int(count.read_text()) + 1 if count.exists() else 1
count.write_text(str(n))
folder = Path('output/checkpoint'); folder.mkdir(exist_ok=True)
(folder / f'checkpoint_2026110{n}T230000.np1.json').write_text('{}')
if n == 3:
    Path('output/clean_exit').touch()
''')
    change(project_file.parent / 'model.json', lambda r: r['checkpoint'].update(
        save_checkpoint=True, on_wallclock_limit=True))
    change(project_file, lambda r: r['model'].update(command=[sys.executable, str(model)], max_runs=5,
           job={'mode': 'pbs', 'walltime': '06:00:00', 'poll_seconds': .001}))
    return project_file


def chain(project_file):
    return next(p for p in (load_project(project_file).work / 'jobs').glob('*-chm-chain-*') if p.is_dir())


def test_backfill_queues_linked_jobs_and_stops_after_completion(pbs_project, monkeypatch):
    scheduler = Scheduler(monkeypatch)
    processed = []
    monkeypatch.setattr('snowcast_runner.rasters.postprocess', lambda p: processed.append(p.id) or {})
    assert main(['run', str(pbs_project)]) == 0
    assert len(scheduler.submissions) == 5
    assert [j['dependency'] for j in scheduler.jobs.values()] == [None, '1.server', '2.server', '3.server', '4.server']
    project = load_project(pbs_project)
    assert (project.work / 'chm/runs').read_text() == '3'
    assert processed == ['west']
    # A remaining allocation stops before setup/CHM, even after a new prepare.
    assert main(['prepare', str(pbs_project)]) == 0
    scheduler.start('5.server')
    assert scheduler.jobs['4.server']['code'] == 99
    assert scheduler.jobs['5.server']['code'] == 271
    assert (project.work / 'chm/runs').read_text() == '3'
    assert not list((project.work / 'jobs').glob('*.pending.json'))
    assert json.loads((chain(pbs_project) / 'finished.json').read_text())['state'] == 'completed'


def test_chain_continues_after_disconnect_and_recovery_does_not_resubmit(pbs_project, monkeypatch):
    scheduler = Scheduler(monkeypatch)
    scheduler.disconnect = True
    assert main(['run', str(pbs_project), '--no-postprocess']) == 1
    assert len(scheduler.jobs) == 5  # The full chain was queued before waiting.
    scheduler.disconnect = False
    scheduler.start('5.server')  # PBS continues without a SnowCast process.
    project = load_project(pbs_project)
    assert (project.work / 'chm/runs').read_text() == '3'
    snapshot = (project.work / 'chm/config.json').read_bytes()
    processed = []
    monkeypatch.setattr('snowcast_runner.rasters.postprocess', lambda p: processed.append(p.id) or {})
    assert main(['run', str(pbs_project)]) == 0
    assert len(scheduler.jobs) == 5 and processed == ['west']
    assert (project.work / 'chm/config.json').read_bytes() == snapshot


@pytest.mark.parametrize('mode', ['error', 'no_progress', 'limit', 'no_data'])
def test_chain_failure_limits_and_no_data(pbs_project, monkeypatch, mode, capsys):
    scheduler = Scheduler(monkeypatch)
    if mode == 'limit':
        change(pbs_project, lambda r: r['model'].update(max_runs=2))
    else:
        code = {'error': 8, 'no_progress': 0, 'no_data': 30}[mode]
        change(pbs_project, lambda r: r['model'].update(
            command=[sys.executable, '-c', f'import sys; sys.exit({code})'],
            no_data_codes=[30] if mode == 'no_data' else []))
    processed = []
    monkeypatch.setattr('snowcast_runner.rasters.postprocess', lambda p: processed.append(True))
    assert main(['run', str(pbs_project)]) == (0 if mode == 'no_data' else 1)
    assert processed == []
    state = json.loads((chain(pbs_project) / 'finished.json').read_text())
    assert state['state'] == ('up_to_date' if mode == 'no_data' else 'failed')
    if mode == 'limit':
        assert 'after 2 PBS jobs' in capsys.readouterr().err
        assert len(list((load_project(pbs_project).work / 'chm/output/checkpoint').glob('*.json'))) == 2
    scheduler.start(list(scheduler.jobs)[-1])
    if mode != 'limit':
        assert 'code' in scheduler.jobs['2.server']


def test_finished_history_recovers_a_missing_wrapper_exit(pbs_project, monkeypatch):
    scheduler = Scheduler(monkeypatch)
    scheduler.lose_exit.add('1.server')
    assert main(['run', str(pbs_project), '--no-postprocess']) == 0
    history = json.loads((chain(pbs_project) / 'segment-001.pbs.json').read_text())
    assert history == {'job_id': '1.server', 'job_state': 'F', 'exit_status': 0, 'source': 'qstat -xf'}
    assert (load_project(pbs_project).work / 'chm/runs').read_text() == '3'


def test_uncertain_submission_is_retained_without_duplicate_jobs(pbs_project, monkeypatch):
    scheduler = Scheduler(monkeypatch)
    run = scheduler.run
    def lose_ack(command, **kwargs):
        result = run(command, **kwargs)
        if command[0] == 'qsub' and len(scheduler.jobs) == 2:
            raise OSError('lost acknowledgement')
        return result
    monkeypatch.setattr(subprocess, 'run', lose_ack)
    assert main(['run', str(pbs_project), '--no-postprocess']) == 1
    assert len(scheduler.jobs) == 2
    assert main(['run', str(pbs_project), '--no-postprocess']) == 1
    assert len(scheduler.jobs) == 2
    assert json.loads((chain(pbs_project) / 'segment-002.pending.json').read_text())['state'] == 'submitting'


def test_only_run_completes_a_partially_submitted_chain(pbs_project, monkeypatch):
    scheduler = Scheduler(monkeypatch)
    from snowcast_runner import backfill
    submit = backfill.submit_pbs
    def interrupted(*args, **kwargs):
        if kwargs['token'] == 'segment-002':
            raise OSError('interrupted before submission')
        return submit(*args, **kwargs)
    monkeypatch.setattr(backfill, 'submit_pbs', interrupted)
    assert main(['run', str(pbs_project), '--no-postprocess']) == 1
    assert main(['prepare', str(pbs_project)]) == 1
    assert len(scheduler.jobs) == 1
    monkeypatch.setattr(backfill, 'submit_pbs', submit)
    assert main(['run', str(pbs_project), '--no-postprocess']) == 0
    assert len(scheduler.jobs) == 5


def test_chain_requires_checkpoint_resume_configuration(pbs_project, monkeypatch, capsys):
    scheduler = Scheduler(monkeypatch)
    change(pbs_project.parent / 'model.json', lambda r: r['checkpoint'].update(auto_resume=False))
    assert main(['run', str(pbs_project), '--no-postprocess']) == 1
    assert not scheduler.jobs
    assert 'PBS backfills require checkpoint' in capsys.readouterr().err


def test_setup_failure_stops_the_chain_without_running_chm(pbs_project, monkeypatch):
    scheduler = Scheduler(monkeypatch)
    setup = pbs_project.parent / 'failed-setup.sh'
    setup.write_text('return 17\n')
    change(pbs_project, lambda r: r['model']['job'].update(setup=str(setup)))
    assert main(['run', str(pbs_project), '--no-postprocess']) == 1
    assert not (load_project(pbs_project).work / 'chm/runs').exists()
    assert json.loads((chain(pbs_project) / 'finished.json').read_text())['state'] == 'failed'
    scheduler.start('5.server')
    assert scheduler.jobs['2.server']['code'] == 271


@pytest.mark.parametrize('history', [
    subprocess.CompletedProcess([], 153, '', 'Unknown Job Id'),
    subprocess.CompletedProcess([], 1, '', 'Cannot connect to server'),
    subprocess.CompletedProcess([], 0, 'job_state = F\n', ''),
])
def test_missing_history_keeps_chain_pending(pbs_project, monkeypatch, history, capsys):
    scheduler = Scheduler(monkeypatch)
    run = scheduler.run
    def query(command, **kwargs):
        if command[0] == 'qstat':
            if '-xf' in command:
                return history
            return subprocess.CompletedProcess(command, 153, '', 'Unknown Job Id')
        return run(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', query)
    assert main(['run', str(pbs_project), '--no-postprocess']) == 1
    assert main(['prepare', str(pbs_project)]) == 1
    assert len(scheduler.jobs) == 5
    assert list((load_project(pbs_project).work / 'jobs').glob('*.pending.json'))
    assert not (chain(pbs_project) / 'finished.json').exists()
    assert 'cannot be queried' in capsys.readouterr().err


def test_scheduler_failure_without_exit_file_is_reported(pbs_project, monkeypatch, capsys):
    scheduler = Scheduler(monkeypatch)
    run = scheduler.run
    def killed(command, **kwargs):
        if command[0] == 'qstat' and '-xf' in command:
            return subprocess.CompletedProcess(command, 0, 'job_state = F\nExit_status = -29\n', '')
        if command[0] == 'qstat':
            return subprocess.CompletedProcess(command, 153, '', 'Unknown Job Id')
        return run(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', killed)
    assert main(['run', str(pbs_project), '--no-postprocess']) == 1
    assert 'exited with -29' in capsys.readouterr().err
    assert not list((load_project(pbs_project).work / 'jobs').glob('*.pending.json'))


def test_explicit_retry_stays_inside_one_allocation(pbs_project, monkeypatch):
    scheduler = Scheduler(monkeypatch)
    model = pbs_project.parent / 'retry.py'
    model.write_text('''import sys
from pathlib import Path
p = Path('attempt')
if not p.exists():
    p.touch()
    sys.exit(7)
Path('output/clean_exit').touch()
''')
    change(pbs_project, lambda r: r['model'].update(command=[sys.executable, str(model)]))
    change(pbs_project, lambda r: r['model']['job'].update(attempts=2, retry_codes=[7], retry_delay_seconds=.001))
    assert main(['run', str(pbs_project), '--no-postprocess']) == 0
    assert scheduler.jobs['1.server']['code'] == 0
    assert 'code' not in scheduler.jobs['2.server']


@pytest.mark.parametrize('wrapper', ['function', 'alias'])
def test_mpi_uses_the_prepared_batch_shell(pbs_project, monkeypatch, wrapper):
    """A PATH-only subprocess silently drops site-specific MPI wrapper options."""
    scheduler = Scheduler(monkeypatch)
    folder = pbs_project.parent / 'MPI tools with spaces'
    folder.mkdir()
    launcher = folder / 'mpirun'
    launcher.write_text(f'#!{sys.executable}\n' + '''import os, subprocess, sys
from pathlib import Path
assert sys.argv[1:4] == ['--cluster-transport', '-n', '1'], sys.argv
assert Path(os.readlink(f'/proc/{os.getppid()}/exe')).name == 'bash'
assert sys.argv[-1] == 'literal argument; $(touch injected)'
raise SystemExit(subprocess.call(sys.argv[4:]))
''')
    launcher.chmod(0o755)
    setup = folder / 'setup.sh'
    setup.write_text(f'export PATH={shlex.quote(str(folder))}:"$PATH"\n'
                     'echo setup >> setup-count\n' +
                     ('mpirun() { command mpirun --cluster-transport "$@"; }\n'
                      if wrapper == 'function' else
                      "shopt -s expand_aliases\nalias mpirun='command mpirun --cluster-transport'\n"))
    change(pbs_project, lambda r: r['model']['job'].update(setup=str(setup), launcher=['mpirun', '-n', '{ranks}']))
    change(pbs_project, lambda r: r['model']['command'].append('literal argument; $(touch injected)'))
    assert main(['run', str(pbs_project), '--no-postprocess']) == 0
    cwd = load_project(pbs_project).work / 'chm'
    assert (cwd / 'runs').read_text() == '3'
    assert (cwd / 'setup-count').read_text().splitlines() == ['setup'] * 3
    assert not (cwd / 'injected').exists()
    scheduler.start('5.server')
    assert (cwd / 'setup-count').read_text().splitlines() == ['setup'] * 3


def test_retry_reduces_remaining_walltime(pbs_project, monkeypatch):
    Scheduler(monkeypatch)
    model = pbs_project.parent / 'retry_budget.py'
    model.write_text('''import json, os, sys, time
from pathlib import Path
p = Path('budgets.json')
budgets = json.loads(p.read_text()) if p.exists() else []
h, m, s = map(int, os.environ['CHM_WALLCLOCK_LIMIT'].split(':'))
budgets.append(h * 3600 + m * 60 + s)
p.write_text(json.dumps(budgets))
if len(budgets) == 1:
    time.sleep(1.1)
    sys.exit(7)
Path('output/clean_exit').touch()
''')
    change(pbs_project, lambda r: r['model'].update(command=[sys.executable, str(model)]))
    change(pbs_project, lambda r: r['model']['job'].update(attempts=2, retry_codes=[7], retry_delay_seconds=.001))
    assert main(['run', str(pbs_project), '--no-postprocess']) == 0
    budgets = json.loads((load_project(pbs_project).work / 'chm/budgets.json').read_text())
    assert len(budgets) == 2 and 0 < budgets[1] < budgets[0] <= 21600


def test_previously_queued_worker_command_remains_supported(pbs_project, monkeypatch):
    from snowcast_runner.jobs import script_text

    scheduler = Scheduler(monkeypatch)
    scheduler.disconnect = True
    assert main(['run', str(pbs_project), '--no-postprocess']) == 1
    directory = chain(pbs_project)
    spec = json.loads((directory / 'request.json').read_text())
    # Recreate the exact entry point used by scripts queued before this fix.
    script = scheduler.jobs['1.server']['script']
    script.write_text(script_text([spec['python'], '-m', 'snowcast_runner.backfill',
                                 str(directory / 'request.json'), '0'],
                                 Path(spec['cwd']), script.with_suffix('.exit'), spec['job']['setup'],
                                 directory / 'finished.json'))
    scheduler.disconnect = False
    assert main(['run', str(pbs_project), '--no-postprocess']) == 0
    assert (load_project(pbs_project).work / 'chm/runs').read_text() == '3'
