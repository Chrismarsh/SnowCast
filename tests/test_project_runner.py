from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
import xarray as xr

from snowcast_runner.cli import main
from snowcast_runner.jobs import execute, resume_pending, wait_pbs
from snowcast_runner.model import prepare, prune_checkpoints
from snowcast_runner.project import load_project, job_config, validate_inputs
from snowcast_runner.rasters import accept_exports
from snowcast_runner.site import publish_domain, deploy_ui
from snowcast_runner.state import workspace


@pytest.fixture
def project_file(tmp_path):
    (tmp_path / 'mesh').write_text('fixture mesh')
    forcing = tmp_path / 'forcing.nc'
    xr.Dataset({'t': ('time', [1.0, 2.0])}, coords={'time': np.array(['2026-11-08T23:00', '2026-11-09T23:00'], dtype='datetime64[ns]')}).to_netcdf(forcing)
    (tmp_path / 'forcing.json').write_text(json.dumps([{'start_time': '20261108T230000', 'end_time': '20261109T230000', 'file_name': 'forcing.nc'}]))
    (tmp_path / 'model.json').write_text(json.dumps({'meshes': {'mesh': 'mesh'}, 'option': {},
                                                  'output': {'ugrid': {'specific_time': '23:00'}}, 'checkpoint': {'auto_resume': True}}))
    path = tmp_path / 'snowcast.json'
    path.write_text(json.dumps({'version': 1, 'id': 'test-project', 'work_root': 'work',
                               'defaults': {'model': {'config': 'model.json'}, 'forcing': {'index': 'forcing.json'}},
                               'domains': [{'id': name, 'name': name.title()} for name in ('west', 'arctic', 'third')]}))
    return path


def change(path, callback):
    raw = json.loads(path.read_text())
    callback(raw)
    path.write_text(json.dumps(raw))


def raster(path, stamp='20261109T230000', variable='swe', transform=None):
    path.mkdir(parents=True, exist_ok=True)
    filename = path / f'{variable}-0.001x0.001_{stamp}.tiff'
    data = np.full((32, 32), 125.25, dtype='float32')
    data[0, 0] = -9999
    with rasterio.open(filename, 'w', driver='GTiff', count=1, width=32, height=32, dtype='float32',
                       crs='EPSG:4326', nodata=-9999, transform=transform or from_origin(-116, 52, .001, .001)) as dst:
        dst.write(data, 1)
        dst.scales = (.1,); dst.offsets = (2,)
        mask = np.full((32, 32), 255, dtype='uint8'); mask[1, 1] = 0
        dst.write_mask(mask)
    return filename


def exports(path):
    for variable in ('swe', 'snowdepthavg', 't'):
        raster(path, variable=variable)
    return path


def test_project_paths_and_defaults_do_not_depend_on_cwd(project_file, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path.parent)
    project = load_project(project_file)
    validate_inputs(project)
    assert len(project.domains) == 3
    assert project.domain('arctic').work == tmp_path / 'work' / 'arctic'
    assert project.domain('west').model['config'] == tmp_path / 'model.json'
    assert main(['validate', str(project_file)]) == 0
    assert not project.work_root.exists()  # Validation is read-only.
    assert main(['run', str(project_file)]) == 1  # Domain choice is explicit.


@pytest.mark.parametrize('mutate', [
    lambda r: r.update(version=2),
    lambda r: r.update(work_root='.'),
    lambda r: r['domains'].append({'id': 'west'}),
    lambda r: r['domains'][0].update(id='../escape'),
    lambda r: r['defaults']['model'].update(output_file='../other.nc'),
    lambda r: r['defaults']['model'].update(checkpoint_keep_days=0),
    lambda r: r['defaults'].update(postprocess={'variables': ['unknown']}),
    lambda r: r['defaults'].update(postprocess={'grid': {'resoluton': [.001, .001]}}),
    lambda r: r['defaults'].update(postprocess={'grid': {'resolution': [0, 1]}}),
    lambda r: r['defaults'].update(postprocess={'grid': {'bounds': [1, 2, 0, 3]}}),
    lambda r: r['defaults']['model'].update(job={'ranks': 2}),
    lambda r: r['defaults']['model'].update(job={'mode': 'pbs', 'ranks': 2, 'launcher': ['mpirun'], 'nodes': 1}),
    lambda r: r['defaults']['model'].update(assets={'output': 'mesh'}),
])
def test_invalid_configuration_is_rejected_before_running(project_file, mutate):
    change(project_file, mutate)
    with pytest.raises(ValueError):
        load_project(project_file)
    assert not (project_file.parent / 'work').exists()


def test_workspace_locks_and_ownership_are_independent(project_file):
    project = load_project(project_file)
    with workspace(project, project.domain('west')):
        with pytest.raises(RuntimeError, match='already running'):
            with workspace(project, project.domain('west')):
                pass
        with workspace(project, project.domain('arctic')):
            pass
    change(project_file, lambda r: r.update(id='another-project'))
    other = load_project(project_file)
    with pytest.raises(ValueError, match='different project'):
        with workspace(other, other.domain('west')):
            pass


def test_generated_model_and_forcing_leave_inputs_unchanged(project_file):
    project = load_project(project_file); domain = project.domain('west')
    original = domain.model['config'].read_bytes()
    with workspace(project, domain):
        target, latest, _ = prepare(domain)
        config = json.loads(target.read_text())
    assert domain.model['config'].read_bytes() == original
    assert config['output']['output_dir'] == str(domain.work / 'chm' / 'output')
    assert config['checkpoint']['auto_resume'] is True
    assert latest == '20261109T230000'
    assert json.loads(Path(config['forcing']['file']).read_text())[0]['file_name'] == str(project_file.parent / 'forcing.nc')


def test_forcing_glob_and_mesh_rank_validation(project_file):
    change(project_file, lambda r: r['defaults'].update(forcing={'glob': 'forcing*.nc'}))
    project = load_project(project_file); domain = project.domain('west')
    with workspace(project, domain):
        prepare(domain)
        model = json.loads(domain.model['config'].read_text())
        (project_file.parent / 'mesh.np800.partition').write_text('partition fixture')
        model['meshes']['mesh'] = 'mesh.np800.partition'
        domain.model['config'].write_text(json.dumps(model))
        with pytest.raises(ValueError, match='partition ranks'):
            prepare(domain)


def test_three_domains_execute_and_one_failure_does_not_stop_others(project_file):
    # Exercise real separate CLI processes, with CHM stand-ins writing domain outputs.
    fake = project_file.parent / 'model.py'
    fake.write_text('import json, pathlib, sys\nc=json.load(open(sys.argv[1]))\np=pathlib.Path(c["output"]["output_dir"])\n'
                    'if "arctic" in str(p): sys.exit(8)\n(p/"clean_exit").write_text("done")\n')
    change(project_file, lambda r: r['defaults']['model'].update(command=[sys.executable, str(fake), '{config}']))
    def run(domain):
        return subprocess.run([sys.executable, '-m', 'snowcast_runner', 'run', str(project_file), '--domain', domain,
                               '--no-postprocess'], capture_output=True, text=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, ['west', 'arctic', 'third']))
    assert [p.returncode for p in results] == [0, 1, 0], [p.stderr for p in results]
    project = load_project(project_file)
    assert [json.loads((d.work / 'status.json').read_text())['state'] for d in project.domains] == ['completed', 'failed', 'completed']


def test_a_missing_other_domain_does_not_prevent_selected_run(project_file):
    change(project_file, lambda r: r['domains'][1].update(model={'config': 'missing.json'}))
    change(project_file, lambda r: r['defaults']['model'].update(command=[sys.executable, '-c', 'import sys; sys.exit(30)'], no_data_codes=[30]))
    assert main(['run', str(project_file), '--domain', 'west']) == 0
    project = load_project(project_file)
    assert json.loads((project.domain('west').work / 'status.json').read_text())['state'] == 'up_to_date'
    assert not project.domain('arctic').work.exists()


def test_zero_exit_without_completion_or_checkpoint_progress_fails_immediately(project_file):
    change(project_file, lambda r: r['defaults']['model'].update(command=[sys.executable, '-c', 'pass']))
    assert main(['run', str(project_file), '--domain', 'west', '--no-postprocess']) == 1
    domain = load_project(project_file).domain('west')
    assert len(list((domain.work / 'jobs').glob('*.sh'))) == 1


def test_wallclock_checkpoint_continues_to_success(project_file):
    fake = project_file.parent / 'checkpoint_model.py'
    fake.write_text('''from pathlib import Path
folder = Path('output/checkpoint'); folder.mkdir(exist_ok=True)
checkpoint = folder / 'checkpoint_20261108T230000.np1.json'
if checkpoint.exists():
    Path('output/clean_exit').touch()
else:
    checkpoint.write_text('{}')
''')
    change(project_file, lambda r: r['defaults']['model'].update(command=[sys.executable, str(fake)]))
    assert main(['prepare', str(project_file), '--domain', 'west']) == 0
    domain = load_project(project_file).domain('west')
    assert not (domain.work / 'jobs').exists()
    assert main(['run', str(project_file), '--domain', 'west', '--no-postprocess']) == 0
    assert len(list((domain.work / 'jobs').glob('*.sh'))) == 2


def test_local_timeout_and_retry_are_explicit(project_file):
    project = load_project(project_file); domain = project.domain('west')
    with workspace(project, domain):
        retry = job_config({'attempts': 2, 'retry_codes': [7], 'retry_delay_seconds': .01}, project.file.parent)
        command = [sys.executable, '-c', 'from pathlib import Path; import sys; p=Path("attempt"); old=p.exists(); p.touch(); sys.exit(0 if old else 7)']
        code, _ = execute(command, work=domain.work, cwd=domain.work, job=retry, label='retry')
        assert code == 0
        timeout = job_config({'timeout_seconds': .1}, project.file.parent)
        with pytest.raises(subprocess.TimeoutExpired):
            execute([sys.executable, '-c', 'import time; time.sleep(10)'], work=domain.work, cwd=domain.work, job=timeout, label='timeout')


def test_failure_notification_is_opt_in_and_does_not_mask_errors(project_file, monkeypatch, capsys):
    from snowcast_runner import notifications
    change(project_file, lambda r: r.update(notifications={'webhook_env': 'TEST_SNOWCAST_HOOK'}))
    project = load_project(project_file)
    monkeypatch.setenv('TEST_SNOWCAST_HOOK', 'https://example.invalid/secret')
    calls = []
    def fail(request, **kwargs):
        calls.append(json.loads(request.data))
        raise OSError('https://example.invalid/secret')
    monkeypatch.setattr(notifications, 'urlopen', fail)
    notifications.notify_failure(project, project.domain('west'), 'run', RuntimeError('job failed'))
    assert calls == [{'text': 'SnowCast test-project/west failed during run: job failed'}]
    output = capsys.readouterr().err
    assert 'could not be delivered' in output and 'secret' not in output


def test_executable_paths_preserve_virtual_environment_symlinks(project_file, tmp_path):
    link = tmp_path / 'venv-python'; link.symlink_to(sys.executable)
    change(project_file, lambda r: r['defaults']['model'].update(command=['./venv-python', '-V']))
    assert load_project(project_file).domain('west').model['command'][0] == str(link)


def test_pbs_pending_state_is_not_silently_resubmitted(project_file, monkeypatch):
    project = load_project(project_file); domain = project.domain('west')
    with workspace(project, domain):
        job = job_config({'mode': 'pbs'}, project.file.parent)
        calls = []
        def run(command, **kw):
            calls.append(command)
            if command[0] == 'qsub':
                raise OSError('connection lost during submit')
            raise AssertionError(command)
        monkeypatch.setattr(subprocess, 'run', run)
        with pytest.raises(OSError):
            execute(['true'], work=domain.work, cwd=domain.work, job=job, label='west')
        with pytest.raises(RuntimeError, match='acknowledgement missing'):
            resume_pending(domain.work)
        assert len(calls) == 1
        pending = next((domain.work / 'jobs').glob('*.pending.json'))
        record = json.loads(pending.read_text()); record.update(state='submitted', job_id='42.server')
        pending.write_text(json.dumps(record))
        monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 1))
        with pytest.raises(RuntimeError, match='cannot be queried'):
            wait_pbs(pending)
        assert pending.exists()
        Path(record['result']).write_text('0\n')
        resume_pending(domain.work)
        assert not pending.exists()


def test_checkpoint_pruning_keeps_daily_groups_and_other_domains(project_file):
    project = load_project(project_file); domain = project.domain('west')
    with workspace(project, domain):
        folder = domain.work / 'chm' / 'output' / 'checkpoint'; folder.mkdir(parents=True)
        for stamp in ['20261105T120000', '20261105T230000', '20261106T230000', '20261107T230000', '20261108T230000']:
            (folder / f'checkpoint_{stamp}.np1.json').write_text('{}')
            (folder / stamp).mkdir()
        other = project.domain('arctic').work / 'chm' / 'output' / 'checkpoint'; other.mkdir(parents=True)
        sentinel = other / 'checkpoint_20261101T230000.np1.json'; sentinel.write_text('{}')
        prune_checkpoints(domain)
        assert len(list(folder.glob('*.json'))) == 3
        assert sentinel.exists()


def test_exports_preserve_values_masks_and_fixed_grid(project_file, tmp_path):
    project = load_project(project_file); domain = project.domain('west')
    with workspace(project, domain):
        source = exports(tmp_path / 'exports')
        accept_exports(domain, source)
        current = domain.work / 'postprocess' / 'tiff'
        with rasterio.open(current / 'swe-0.001x0.001_20261109T230000.tiff') as output:
            assert output.scales == (.1,) and output.offsets == (2,)
            assert output.read(1)[2, 2] == 125.25
            assert output.read_masks(1)[0, 0] == output.read_masks(1)[1, 1] == 0
            assert output.transform == from_origin(-116, 52, .001, .001)
        before = {f.name: f.read_bytes() for f in current.iterdir()}
        raster(source, transform=from_origin(-115, 52, .001, .001))
        with pytest.raises(ValueError, match='Source grid changed'):
            accept_exports(domain, source)
        assert before == {f.name: f.read_bytes() for f in current.iterdir()}


def test_missing_exports_do_not_rotate_current_data(project_file, tmp_path):
    project = load_project(project_file); domain = project.domain('west')
    with workspace(project, domain):
        source = exports(tmp_path / 'exports')
        accept_exports(domain, source)
        (source / 't-0.001x0.001_20261109T230000.tiff').unlink()
        with pytest.raises(ValueError, match='every requested variable'):
            accept_exports(domain, source)
        assert len(list((domain.work / 'postprocess' / 'tiff').glob('*.tiff'))) == 3


def test_original_tiff_keeps_float64_precision_while_cog_is_float32(project_file, tmp_path):
    change(project_file, lambda r: r['defaults'].update(postprocess={'variables': ['swe']}))
    project = load_project(project_file); domain = project.domain('west')
    source = tmp_path / 'exports'; source.mkdir()
    values = np.linspace(1.123456789, 400.987654321, 32 * 32).reshape(32, 32)
    with rasterio.open(source / 'swe-0.001x0.001_20261109T230000.tiff', 'w', driver='GTiff',
                       count=1, width=32, height=32, crs='EPSG:4326', dtype='float64', nodata=-9999,
                       transform=from_origin(-116, 52, .001, .001)) as dst:
        dst.write(values, 1)
    with workspace(project, domain):
        accept_exports(domain, source)
        with rasterio.open(next((domain.work / 'postprocess' / 'tiff').glob('*.tiff'))) as data:
            assert data.dtypes == ('float64',)
            np.testing.assert_array_equal(data.read(1), values)
        catalogue = publish_domain(project, domain, tmp_path / 'site')
        asset = catalogue['variables'][0]['assets'][0]
        with rasterio.open(tmp_path / 'site' / 'data' / project.id / domain.id / asset['path']) as data:
            assert data.dtypes == ('float32',)
            np.testing.assert_array_equal(data.read(1), values.astype('float32'))


def test_projected_grid_and_optional_ascii_with_physical_values(project_file, tmp_path):
    change(project_file, lambda r: r['defaults'].update(postprocess={'grid': {'crs': 'EPSG:32611', 'resolution': [100, 100]},
                                                                   'ascii': {'enabled': True, 'resolution': .001}}))
    project = load_project(project_file); domain = project.domain('arctic')
    with workspace(project, domain):
        source = exports(tmp_path / 'exports'); accept_exports(domain, source)
        with rasterio.open(next((domain.work / 'postprocess' / 'tiff').glob('swe*.tiff'))) as data:
            assert data.crs.to_epsg() == 32611
            assert data.res == (100, 100)
        with rasterio.open(next((domain.work / 'postprocess' / 'ascii').glob('swe*.asc'))) as data:
            assert data.crs.is_geographic and data.crs.to_dict()['datum'] == 'WGS84'
            assert data.nodata == -9999
            assert data.read(1)[2, 2] == pytest.approx(14.525)
        assert not list((domain.work / 'postprocess' / 'ascii').glob('snowdepthavg*'))


def test_concurrent_publications_merge_registry_and_cleanup_isolated(project_file, tmp_path):
    project = load_project(project_file); source = exports(tmp_path / 'exports'); site = tmp_path / 'site'
    for domain in project.domains:
        with workspace(project, domain):
            accept_exports(domain, source)
    with ThreadPoolExecutor(max_workers=3) as pool:
        catalogues = list(pool.map(lambda d: publish_domain(project, d, site), project.domains))
    registry = json.loads((site / 'domains.json').read_text())
    assert {entry['id'] for entry in registry['domains']} == {'test-project/west', 'test-project/arctic', 'test-project/third'}
    assert len({c['variables'][0]['assets'][0]['id'] for c in catalogues}) == 3
    arctic = site / 'data' / 'test-project' / 'arctic' / 'catalog.json'
    before = arctic.read_bytes()
    publish_domain(project, project.domain('west'), site)
    assert arctic.read_bytes() == before
    assert len(json.loads((site / 'domains.json').read_text())['domains']) == 3


def test_ui_deployment_preserves_data_registry_and_live_download_index(tmp_path):
    dist, site = tmp_path / 'dist', tmp_path / 'site'
    dist.mkdir(); site.mkdir()
    (dist / 'index.html').write_text('<html>new UI</html>')
    (dist / 'assets').mkdir(); (dist / 'assets' / 'new.js').write_text('new')
    for name in ['domains.json', 'download-index.json']:
        (site / name).write_text('live')
        (dist / name).write_text('stale build')
    (site / 'data').mkdir(); (site / 'data' / 'catalog.json').write_text('live data')
    (dist / 'data').mkdir(); (dist / 'data' / 'catalog.json').write_text('stale data')
    deploy_ui(dist, site)
    assert (site / 'index.html').read_text() == '<html>new UI</html>'
    assert (site / 'data' / 'catalog.json').read_text() == 'live data'
    assert (site / 'domains.json').read_text() == (site / 'download-index.json').read_text() == 'live'


def test_runner_to_postprocessing_uses_configured_commands_and_actual_output(project_file, tmp_path):
    fake_model = tmp_path / 'fake_model.py'
    fake_model.write_text('''import json, pathlib, sys
import numpy as np
import xarray as xr
c = json.load(open(sys.argv[1]))
output = pathlib.Path(c['output']['output_dir'])
times = np.array(['2026-11-08T23:00', '2026-11-09T23:00'], dtype='datetime64[ns]')
xr.Dataset({v: ('time', [1., 2.]) for v in c['output']['ugrid']['variables']}, coords={'time': times}).to_netcdf(output / 'custom.nc')
(output / 'clean_exit').touch()
''')
    exporter = tmp_path / 'fake_exporter'
    exporter.write_text(f'#!{sys.executable}\n' + '''import argparse, pathlib
import numpy as np
import rasterio
from rasterio.transform import from_origin
import xarray as xr
p = argparse.ArgumentParser()
p.add_argument('input'); p.add_argument('--dxdy'); p.add_argument('--method')
p.add_argument('--timeoffset', nargs='+', type=int); p.add_argument('--variables', nargs='+')
p.add_argument('--tiff-output'); p.add_argument('--overwrite', action='store_true')
a = p.parse_args()
out = pathlib.Path(a.tiff_output); out.mkdir(parents=True, exist_ok=True)
with xr.open_dataset(a.input) as ds:
    for offset in a.timeoffset:
        stamp = ds.time[offset].dt.strftime('%Y%m%dT%H%M%S').item()
        for var in a.variables:
            with rasterio.open(out / f'{var}-{a.dxdy}x{a.dxdy}_{stamp}.tiff', 'w', driver='GTiff', count=1,
                               width=32, height=32, crs='EPSG:4326', dtype='float32', nodata=-9999,
                               transform=from_origin(-116, 52, float(a.dxdy), float(a.dxdy))) as dst:
                dst.write(np.full((32, 32), ds[var][offset].item(), dtype='float32'), 1)
''')
    exporter.chmod(0o755)
    change(project_file, lambda r: r['defaults']['model'].update(command=[sys.executable, str(fake_model), '{config}'], output_file='custom.nc'))
    change(project_file, lambda r: r['defaults'].update(postprocess={'exporter': str(exporter), 'variables': ['swe', 'snowdepthavg']}))
    assert main(['run', str(project_file), '--domain', 'west']) == 0
    domain = load_project(project_file).domain('west')
    tiffs = domain.work / 'postprocess' / 'tiff'
    assert len(list(tiffs.glob('*.tiff'))) == 4
    state = json.loads((domain.work / 'status.json').read_text())
    assert state['output']['times'] == ['20261108T230000', '20261109T230000']
    assert not list((domain.work / 'postprocess' / 'ascii').iterdir())
    assert main(['publish', str(project_file), '--domain', 'west', '--site-dir', str(tmp_path / 'site')]) == 0
    assert (tmp_path / 'site' / 'domains.json').exists()


def test_pbs_script_executes_setup_and_persists_exit_status(project_file, monkeypatch):
    project = load_project(project_file); domain = project.domain('west')
    setup = project_file.parent / 'setup.sh'; setup.write_text('export TEST_SETTING=ready\n')
    job = job_config({'mode': 'pbs', 'setup': str(setup), 'nodes': 2, 'cpus_per_node': 4, 'ranks_per_node': 2,
                      'ranks': 4, 'launcher': ['env', 'TEST_RANKS={ranks}']}, project_file.parent)
    real_run = subprocess.run
    calls = []
    def qsub(command, **kwargs):
        calls.append(command)
        assert command[0] == 'qsub'
        assert 'select=2:ncpus=4:mpiprocs=2:mem=4gb' in command
        result = real_run(['bash', command[-1]], capture_output=True, text=True,
                          env={**os.environ, 'PBS_JOBID': '123.server', 'SNOWCAST_WALLTIME': '01:00:00'})
        assert result.returncode == 0, result.stderr
        return subprocess.CompletedProcess(command, 0, '123.server\n', '')
    monkeypatch.setattr(subprocess, 'run', qsub)
    with workspace(project, domain):
        code, _ = execute([sys.executable, '-c', 'import os; assert os.environ["TEST_SETTING"] == "ready"; assert os.environ["TEST_RANKS"] == "4"; assert os.environ["CHM_WALLCLOCK_LIMIT"] == "01:00:00"'],
                          work=domain.work, cwd=domain.work, job=job, label='pbs')
        assert code == 0 and len(calls) == 1
        assert not list((domain.work / 'jobs').glob('*.pending.json'))


def test_local_job_retains_domain_lock_after_runner_is_killed(project_file):
    fake = project_file.parent / 'long_model.py'
    fake.write_text('import os, pathlib, time\npathlib.Path("running").write_text(str(os.getpid()))\ntime.sleep(20)\n')
    change(project_file, lambda r: r['defaults']['model'].update(command=[sys.executable, str(fake)]))
    project = load_project(project_file); domain = project.domain('west')
    runner = subprocess.Popen([sys.executable, '-m', 'snowcast_runner', 'run', str(project_file), '--domain', 'west', '--no-postprocess'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    child_pid = None
    try:
        marker = domain.work / 'chm' / 'running'
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert marker.exists()
        child_pid = int(marker.read_text())
        runner.kill(); runner.wait()
        with pytest.raises(RuntimeError, match='already running'):
            with workspace(project, domain):
                pass
    finally:
        import signal
        if child_pid:
            try:
                os.killpg(os.getpgid(child_pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if runner.poll() is None:
            runner.kill(); runner.wait()


def test_site_parent_permissions_and_catalogue_ranges(project_file, tmp_path):
    change(project_file, lambda r: r['domains'][0].update(display={'ranges': {'swe': [0, 200]}}))
    project = load_project(project_file); domain = project.domain('west')
    site = tmp_path / 'site'
    with workspace(project, domain):
        accept_exports(domain, exports(tmp_path / 'exports'))
        old = os.umask(0o077)
        try:
            catalogue = publish_domain(project, domain, site)
        finally:
            os.umask(old)
    for folder in (site, site / 'data', site / 'data' / project.id):
        assert folder.stat().st_mode & 0o777 == 0o755
    assert catalogue['variables'][0]['range'] == [0, 200]
