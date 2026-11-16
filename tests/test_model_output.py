"""A migrated checkpoint must never redirect writes into a legacy NetCDF."""
import json
import shutil

import numpy as np
import pytest
import xarray as xr

from snowcast_runner.cli import main
from snowcast_runner.project import load_project
from test_project_runner import project_file, change, configure_fake_pipeline
from test_pbs_backfill import pbs_project, Scheduler


def test_generated_output_name_matches_postprocessor_and_preserves_authored_config(project_file):
    change(project_file, lambda r: r['model'].update(output_file='domain.nc'))
    authored = project_file.parent / 'model.json'
    change(authored, lambda r: r['output'].update(output_dir='/legacy',
           ugrid={'base_name': '/legacy/old-output', 'specific_time': '23:00'}))
    original = authored.read_bytes()
    assert main(['prepare', str(project_file)]) == 0
    config = json.loads((load_project(project_file).work / 'chm/config.json').read_text())
    assert config['output']['output_dir'] == 'output'
    assert config['output']['ugrid']['base_name'] == 'domain'
    assert config['output']['ugrid']['specific_time'] == '23:00'
    assert authored.read_bytes() == original


def test_migrated_output_must_be_copied_and_rebound_before_processing(project_file, tmp_path, capsys):
    configure_fake_pipeline(project_file, tmp_path)
    assert main(['run', str(project_file)]) == 0
    p = load_project(project_file)
    output = p.work / 'chm/output'
    source = output / p.model['output_file']
    legacy = tmp_path / 'legacy-output.nc'
    dates = ['2026-11-14T23:00', '2026-11-15T23:00', '2026-11-16T23:00']
    xr.Dataset({v: ('time', [14., 15., 16.]) for v in p.postprocess['variables']},
               coords={'time': np.array(dates, dtype='datetime64[ns]')}).to_netcdf(legacy)
    checkpoint = output / 'checkpoint/checkpoint_20261116T230000.np1.json'
    checkpoint.parent.mkdir()
    record = {'ranks': 1, 'timestep_counter': 72, 'files': ['20261116T230000/rank0.nc'],
              'ugrid_outputs': [{'base_name': 'old-output', 'path': str(legacy)}]}
    checkpoint.write_text(json.dumps(record))
    before = {path: path.read_bytes() for path in [source, legacy, checkpoint,
              *list((p.work / 'postprocess/tiff').iterdir())]}
    jobs = list((p.work / 'jobs').iterdir())
    capsys.readouterr()
    for action in ('validate', 'prepare', 'run', 'postprocess'):
        assert main([action, str(project_file)]) == 1
        error = capsys.readouterr().err
        assert str(legacy) in error and str(source) in error and str(checkpoint) in error
    assert all(path.read_bytes() == data for path, data in before.items())
    assert list((p.work / 'jobs').iterdir()) == jobs

    # The recovery copies data and changes only the copied checkpoint's output path.
    shutil.copy2(legacy, source)
    record['ugrid_outputs'][0]['path'] = str(source)
    checkpoint.write_text(json.dumps(record))
    change(project_file, lambda r: r['postprocess'].update(recent_steps=3))
    assert main(['prepare', str(project_file)]) == 0
    assert main(['postprocess', str(project_file)]) == 0
    state = json.loads((p.work / 'status.json').read_text())
    assert state['output']['times'] == ['20261114T230000', '20261115T230000', '20261116T230000']
    assert legacy.read_bytes() == before[legacy]
    assert record['files'] == ['20261116T230000/rank0.nc'] and record['timestep_counter'] == 72


@pytest.mark.parametrize('relative', [True, False])
def test_checkpoint_paths_resolve_from_chm_cwd(project_file, relative):
    assert main(['prepare', str(project_file)]) == 0
    p = load_project(project_file)
    cwd = p.work / 'chm'
    folder = cwd / 'output/checkpoint'
    folder.mkdir()
    target = 'output/output.nc' if relative else str(cwd / 'output/output.nc')
    (folder / 'checkpoint_20261109T230000.np1.json').write_text(json.dumps(
        {'ugrid_outputs': [{'base_name': 'output', 'path': target}]}))
    assert main(['prepare', str(project_file)]) == 0


def test_explicit_checkpoint_output_is_checked(project_file, tmp_path):
    legacy = tmp_path / 'legacy.nc'
    checkpoint = tmp_path / 'checkpoint.json'
    checkpoint.write_text(json.dumps({'ugrid_outputs': [{'path': str(legacy)}]}))
    change(project_file.parent / 'model.json', lambda r: r.update(
        checkpoint={'load_checkpoint_path': str(checkpoint)}))
    assert main(['prepare', str(project_file)]) == 1
    assert not (load_project(project_file).work / 'chm/config.json').exists()


def test_output_symlink_cannot_share_legacy_mutable_file(project_file, tmp_path):
    assert main(['prepare', str(project_file)]) == 0
    p = load_project(project_file)
    legacy = tmp_path / 'legacy.nc'
    legacy.write_bytes(b'legacy data')
    (p.work / 'chm/output/output.nc').symlink_to(legacy)
    assert main(['run', str(project_file)]) == 1
    assert main(['postprocess', str(project_file)]) == 1
    assert legacy.read_bytes() == b'legacy data'


def test_postprocess_rejects_staged_legacy_output_config(project_file):
    assert main(['prepare', str(project_file)]) == 0
    p = load_project(project_file)
    config = p.work / 'chm/config.json'
    change(config, lambda r: r['output']['ugrid'].update(base_name='/legacy/output'))
    assert main(['postprocess', str(project_file)]) == 1


@pytest.mark.parametrize('setting', [{'rotate_frequency': 3}, {'format': 'zarr'}])
def test_unsupported_output_layout_fails_before_submitting(project_file, setting):
    change(project_file.parent / 'model.json', lambda r: r['output']['ugrid'].update(setting))
    assert main(['run', str(project_file)]) == 1
    assert not (load_project(project_file).work / 'jobs').exists()


def test_each_pbs_segment_checks_new_checkpoint_output(pbs_project, monkeypatch, tmp_path):
    scheduler = Scheduler(monkeypatch)
    p = load_project(pbs_project)
    model = pbs_project.parent / 'backfill_model.py'
    legacy = tmp_path / 'legacy.nc'
    legacy.write_bytes(b'unchanged legacy output')
    with model.open('a') as f:
        f.write(f'''\nif n == 1:
    (folder / 'checkpoint_20261101T230000.np1.json').write_text(json.dumps(
        {{'ugrid_outputs': [{{'base_name': 'output', 'path': {str(legacy)!r}}}]}}))
''')
    assert main(['run', str(pbs_project), '--no-postprocess']) == 1
    assert (p.work / 'chm/runs').read_text() == '1'
    assert legacy.read_bytes() == b'unchanged legacy output'
    assert len(scheduler.jobs) == 5  # Queued continuations do not launch CHM.
