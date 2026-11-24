"""CLI progress must remain useful in logs without changing command results."""
import json
import re
import subprocess
import sys

import pytest

from snowcast_runner.cli import main
from snowcast_runner.jobs import wait_pbs
from snowcast_runner.progress import reporting
from test_project_runner import project_file, change, configure_fake_pipeline


@pytest.mark.parametrize('quiet', [False, True])
def test_run_reports_export_dates_without_changing_stdout(project_file, tmp_path, capsys, quiet):
    configure_fake_pipeline(project_file, tmp_path)
    assert main(['run', str(project_file), *(['--quiet'] if quiet else [])]) == 0
    output = capsys.readouterr()
    assert output.out == 'west: completed\n'
    if quiet:
        assert output.err == ''
    else:
        assert 'Preparing CHM configuration and forcing' in output.err
        assert 'No checkpoint found' in output.err
        assert 'Postprocessing 2 of 2 available timesteps: 20261108T230000 to 20261109T230000' in output.err
        assert 'Run completed in' in output.err
        assert all(re.match(r'^\[\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\] west: ', line)
                   for line in output.err.splitlines())
    # Reporting must not leak into a subsequent invocation in the same process.
    assert main(['status', str(project_file)]) == 0
    status = capsys.readouterr()
    assert status.err == ''
    assert json.loads(status.out)['state'] == 'completed'


def test_up_to_date_explains_why_postprocess_is_skipped(project_file, capsys):
    assert main(['prepare', str(project_file)]) == 0
    folder = project_file.parent / 'work/chm/output/checkpoint'
    folder.mkdir()
    (folder / 'checkpoint_20261109T230000.np1.json').write_text('{}')
    capsys.readouterr()
    assert main(['run', str(project_file)]) == 0
    output = capsys.readouterr()
    assert output.out == 'west: up_to_date\n'
    assert 'Latest checkpoint: checkpoint_20261109T230000.np1.json' in output.err
    assert 'Postprocessing skipped (model is up to date)' in output.err


def test_quiet_retains_failures(project_file, capsys):
    change(project_file, lambda r: r['model'].update(command=[sys.executable, '-c', 'raise SystemExit(8)']))
    assert main(['run', str(project_file), '-q']) == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert output.err.startswith('SnowCast: west: CHM exit 8; see ')
    assert 'Starting run' not in output.err


@pytest.mark.parametrize('history', [False, True])
def test_pbs_progress_reports_transitions_and_throttles_heartbeats(tmp_path, monkeypatch, capsys, history):
    pending, result = tmp_path / 'job.pending.json', tmp_path / 'job.exit'
    pending.write_text(json.dumps({'state': 'submitted', 'result': str(result), 'qstat': 'qstat',
                                   'job_id': '42.server', 'poll_seconds': 100}))
    clock, sleeps, queries = [0], [], []

    def query(command, **kwargs):
        queries.append(command)
        state = 'Q' if clock[0] < 400 else 'R'
        if history:
            if '-xf' not in command:
                return subprocess.CompletedProcess(command, 153, '', 'Unknown Job Id')
            output = f'Job Id: 42.server\n    job_state = {state}\n'
        else:
            # PBS's table can truncate the server part of a job ID.
            output = f'Job id Name User Time Use S Queue\n42.serv sc_west user 00:00:00 {state} workq\n'
        return subprocess.CompletedProcess(command, 0, output, '')

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
        if clock[0] == 600:
            result.write_text('0\n')

    monkeypatch.setattr('snowcast_runner.jobs.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('snowcast_runner.jobs.time.sleep', sleep)
    monkeypatch.setattr('snowcast_runner.jobs.subprocess.run', query)
    with reporting('west'):
        assert wait_pbs(pending) == 0
    output = capsys.readouterr()
    assert output.out == ''
    assert output.err.count(': queued (waited ') == 2  # Initial state, then five-minute heartbeat.
    assert output.err.count(': running (waited ') == 1
    assert str(tmp_path / 'job.log') in output.err
    assert 'finished with exit 0 (waited 0:10:00)' in output.err
    assert sleeps == [100] * 6
    assert len(queries) == (12 if history else 6)  # Reporting adds no scheduler queries.
    assert not pending.exists()
