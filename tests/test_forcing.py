from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
import xarray as xr

from met.main import update_index, update_metdata_json
from snowcast_runner.cli import main
from snowcast_runner.project import load_project


def daily_file(folder, day):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{day.replace("-", "")}.nc'
    xr.Dataset({'t': ('time', [1., 2.])},
               coords={'time': np.array([f'{day}T00:00', f'{day}T23:00'], dtype='datetime64[ns]')}).to_netcdf(path)
    return path


@pytest.fixture
def project_file(tmp_path):
    archive = tmp_path / 'external-archive'
    daily_file(archive, '2026-11-09')
    (tmp_path / 'hrdps').symlink_to(archive, target_is_directory=True)
    (tmp_path / 'mesh').touch()
    (tmp_path / 'model.json').write_text(json.dumps({'meshes': {'mesh': 'mesh'}}))
    project = tmp_path / 'snowcast.json'
    project.write_text(json.dumps({
        'version': 1, 'id': 'snowcast', 'work_root': 'runs',
        'defaults': {'model': {'config': 'model.json'},
                     'forcing': {'archive': 'hrdps', 'index': 'metadata/metdata-hrdps.json'}},
        'domains': [{'id': 'west'}, {'id': 'arctic'}],
    }))
    return project


def change(project_file, callback):
    raw = json.loads(project_file.read_text())
    callback(raw)
    project_file.write_text(json.dumps(raw))


def test_prepare_creates_link_and_index_then_stages_independent_snapshot(project_file, monkeypatch):
    project = load_project(project_file); domain = project.domain('west')
    archive = domain.forcing['archive']; index = domain.forcing['index']
    source_bytes = next(archive.glob('*.nc')).read_bytes()
    monkeypatch.chdir(project_file.parent.parent)
    assert main(['validate', str(project_file)]) == 0
    assert not index.exists() and not project.work_root.exists()
    assert main(['prepare', str(project_file), '--domain', 'west']) == 0
    link = domain.work / 'met' / 'archive'
    assert link.is_symlink() and link.resolve() == archive
    inode = link.lstat().st_ino
    metadata = json.loads(index.read_text())
    assert metadata == [{'start_time': '20261109T000000', 'end_time': '20261109T230000',
                         'file_name': str(archive / '20261109.nc')}]
    snapshot = domain.work / 'met' / 'index.json'
    config = json.loads((domain.work / 'chm' / 'config.json').read_text())
    assert config['forcing']['file'] == str(snapshot)
    assert json.loads(snapshot.read_text()) == metadata
    assert not (domain.work / 'jobs').exists()
    assert next(archive.glob('*.nc')).read_bytes() == source_bytes
    assert sorted(p.name for p in archive.iterdir()) == ['20261109.nc']

    daily_file(archive, '2026-11-10')
    assert main(['met-update', str(project_file), '--domain', 'west']) == 0
    assert len(json.loads(index.read_text())) == 2
    assert json.loads(snapshot.read_text()) == metadata  # met-update leaves a staged run alone.
    assert main(['prepare', str(project_file), '--domain', 'west']) == 0
    assert len(json.loads(snapshot.read_text())) == 2
    assert link.lstat().st_ino == inode  # Repeated preparation keeps the correct link.


def test_incremental_update_preserves_existing_metadata_and_reads_only_new_files(project_file, monkeypatch):
    domain = load_project(project_file).domain('west')
    archive, index = domain.forcing['archive'], domain.forcing['index']
    update_index(archive, index)
    records = json.loads(index.read_text())
    records[0].update(start_time='20261109T010000', provider='hrdps')
    # A relative entry is recognized as the same physical file through a directory alias.
    records[0]['file_name'] = '../hrdps/20261109.nc'
    index.write_text(json.dumps(records))
    daily_file(archive, '2026-11-08')  # Late arrivals before the last indexed date are included.
    daily_file(archive, '2026-11-10')
    opened = []
    real_open = xr.open_dataset

    def tracked_open(filename, *args, **kwargs):
        opened.append(Path(filename).name)
        return real_open(filename, *args, **kwargs)

    monkeypatch.setattr(xr, 'open_dataset', tracked_open)
    result = update_index(project_file.parent / 'hrdps', index)
    assert result['added'] == 2 and result['files'] == 3
    assert opened == ['20261108.nc', '20261110.nc']
    records = json.loads(index.read_text())
    assert [r['start_time'] for r in records] == ['20261108T000000', '20261109T010000', '20261110T000000']
    assert records[1]['provider'] == 'hrdps'
    before = index.stat().st_mtime_ns, index.read_bytes()
    assert update_index(archive, index)['added'] == 0
    assert (index.stat().st_mtime_ns, index.read_bytes()) == before
    assert opened == ['20261108.nc', '20261110.nc']


def test_concurrent_domains_share_canonical_index_lock(project_file):
    project = load_project(project_file)
    archive = project.domain('west').forcing['archive']
    index = project.domain('west').forcing['index']
    daily_file(archive, '2026-11-10')
    alias = project_file.parent / 'index-alias.json'
    alias.symlink_to(index)
    change(project_file, lambda r: r['domains'][1].update(forcing={
        'archive': str(archive), 'index': 'index-alias.json'}))

    def run(domain):
        return subprocess.run([sys.executable, '-m', 'snowcast_runner', 'met-update', str(project_file),
                               '--domain', domain], capture_output=True, text=True, timeout=15)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ['west', 'arctic']))
    assert [r.returncode for r in results] == [0, 0], [r.stderr for r in results]
    assert sorted(json.loads(r.stdout)['added'] for r in results) == [0, 2]
    assert len(json.loads(index.read_text())) == 2
    assert alias.is_symlink()
    for domain in project.domains:
        assert (domain.work / 'met' / 'archive').resolve() == archive


def test_domains_can_use_separate_archives_and_indices(project_file):
    arctic_archive = project_file.parent / 'arctic-forcing'
    daily_file(arctic_archive, '2026-11-07')
    change(project_file, lambda r: r['domains'][1].update(forcing={
        'archive': 'arctic-forcing', 'index': 'metadata/arctic.json'}))
    for name in ('west', 'arctic'):
        assert main(['prepare', str(project_file), '--domain', name]) == 0
    project = load_project(project_file)
    snapshots = [json.loads((d.work / 'met' / 'index.json').read_text()) for d in project.domains]
    assert [rows[0]['end_time'] for rows in snapshots] == ['20261109T230000', '20261107T230000']
    assert len({rows[0]['file_name'] for rows in snapshots}) == 2


def test_different_domain_archives_cannot_accidentally_share_an_index(project_file):
    change(project_file, lambda r: r['domains'][1].update(forcing={'archive': 'arctic-forcing'}))
    with pytest.raises(ValueError, match='different indexes'):
        load_project(project_file)
    assert not (project_file.parent / 'metadata').exists()


def test_run_updates_met_before_deciding_model_is_up_to_date(project_file):
    fake = project_file.parent / 'model.py'
    fake.write_text('import json, pathlib, sys\nc=json.load(open(sys.argv[1]))\n'
                    'rows=json.load(open(c["forcing"]["file"]))\n'
                    'assert rows[-1]["end_time"] == "20261110T230000"\n'
                    'pathlib.Path(c["output"]["output_dir"], "clean_exit").touch()\n')
    change(project_file, lambda r: r['defaults']['model'].update(command=[sys.executable, str(fake), '{config}']))
    assert main(['prepare', str(project_file), '--domain', 'west']) == 0
    domain = load_project(project_file).domain('west')
    checkpoints = domain.work / 'chm' / 'output' / 'checkpoint'
    checkpoints.mkdir()
    (checkpoints / 'checkpoint_20261109T230000.np1.json').write_text('{}')
    daily_file(domain.forcing['archive'], '2026-11-10')
    assert main(['run', str(project_file), '--domain', 'west', '--no-postprocess']) == 0
    assert json.loads((domain.work / 'status.json').read_text())['state'] == 'completed'


def test_met_update_does_not_require_model_inputs(project_file):
    (project_file.parent / 'model.json').unlink()
    assert main(['met-update', str(project_file), '--domain', 'west']) == 0
    assert not (load_project(project_file).domain('west').work / 'chm').exists()


@pytest.mark.parametrize('kind', ['corrupt', 'no-time', 'empty-time', 'numeric-time'])
def test_bad_new_file_preserves_previous_index(project_file, kind):
    domain = load_project(project_file).domain('west')
    archive, index = domain.forcing['archive'], domain.forcing['index']
    update_index(archive, index)
    before = index.read_bytes()
    daily_file(archive, '2026-11-10')
    bad = archive / '20261111.nc'
    if kind == 'corrupt':
        bad.write_text('incomplete NetCDF')
    elif kind == 'no-time':
        xr.Dataset({'t': ('x', [1.])}).to_netcdf(bad)
    elif kind == 'empty-time':
        xr.Dataset(coords={'time': np.array([], dtype='datetime64[ns]')}).to_netcdf(bad)
    else:
        xr.Dataset(coords={'time': [1., 2.]}).to_netcdf(bad)
    assert main(['met-update', str(project_file), '--domain', 'west']) == 1
    assert index.read_bytes() == before
    assert json.loads((domain.work / 'status.json').read_text())['state'] == 'failed'


@pytest.mark.parametrize('kind', ['directory', 'other-link', 'broken-link', 'met-link'])
def test_prepare_does_not_replace_conflicting_met_paths(project_file, kind):
    domain = load_project(project_file).domain('west')
    folder = domain.work / 'met'
    folder.parent.mkdir(parents=True)
    if kind == 'met-link':
        folder.symlink_to(domain.forcing['archive'], target_is_directory=True)
    else:
        folder.mkdir()
        if kind == 'directory':
            (folder / 'archive').mkdir()
        else:
            (folder / 'archive').symlink_to(project_file.parent / ('mesh' if kind == 'other-link' else 'missing'))
    assert main(['prepare', str(project_file), '--domain', 'west']) == 1
    assert not domain.forcing['index'].exists()
    assert not (domain.forcing['archive'] / 'index.json').exists()


def test_empty_archive_does_not_publish_empty_index(project_file):
    domain = load_project(project_file).domain('west')
    next(domain.forcing['archive'].glob('*.nc')).unlink()
    assert main(['met-update', str(project_file), '--domain', 'west']) == 1
    assert not domain.forcing['index'].exists()


@pytest.mark.parametrize('forcing', [
    {'archive': 'absent', 'index': 'metadata/index.json'},
    {'archive': 'mesh', 'index': 'metadata/index.json'},
    {'archive': 'runs/archive', 'index': 'metadata/index.json'},
    {'archive': 'hrdps', 'index': 'runs/index.json'},
    {'archive': 'hrdps', 'index': 'hrdps'},
])
def test_forcing_validation_is_read_only_and_rejects_invalid_paths(project_file, forcing):
    change(project_file, lambda r: r['defaults'].update(forcing=forcing))
    assert main(['validate', str(project_file)]) == 1
    assert not (project_file.parent / 'runs').exists()
    assert not (project_file.parent / 'metadata').exists()


def test_index_only_domain_can_disable_inherited_archive(project_file):
    domain = load_project(project_file).domain('west')
    update_index(domain.forcing['archive'], domain.forcing['index'])
    change(project_file, lambda r: r['domains'][1].update(forcing={'archive': None}))
    assert main(['prepare', str(project_file), '--domain', 'arctic']) == 0
    arctic = load_project(project_file).domain('arctic')
    assert not (arctic.work / 'met' / 'archive').exists()
    assert main(['met-update', str(project_file), '--domain', 'arctic']) == 1


def test_legacy_updater_uses_the_same_incremental_metadata(project_file, monkeypatch):
    met = project_file.parent / 'met'
    met.mkdir()
    archive = project_file.parent / 'external-archive'
    (met / 'hrdps').symlink_to(archive, target_is_directory=True)
    monkeypatch.chdir(project_file.parent)
    assert update_metdata_json({})['added'] == 1
    index = met / 'metdata-hrdps.json'
    before = index.read_bytes()
    assert update_index(archive, index)['added'] == 0
    assert index.read_bytes() == before
    daily_file(archive, '2026-11-10')
    assert update_metdata_json({})['added'] == 1
    assert len(json.loads(index.read_text())) == 2
