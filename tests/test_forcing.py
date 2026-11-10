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
from project_helpers import clone_project
from snowcast_runner.project import load_project


def daily_file(folder, day):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{day.replace("-", "")}.nc'
    xr.Dataset({'t': ('time', [1., 2.])},
               coords={'time': np.array([f'{day}T00:00', f'{day}T23:00'], dtype='datetime64[ns]')}).to_netcdf(path)
    return path


@pytest.fixture
def project_file(tmp_path):
    tmp_path = tmp_path / 'west'
    tmp_path.mkdir()
    archive = tmp_path / 'external-archive'
    daily_file(archive, '2026-11-09')
    (tmp_path / 'hrdps').symlink_to(archive, target_is_directory=True)
    (tmp_path / 'mesh').touch()
    (tmp_path / 'model.json').write_text(json.dumps({'meshes': {'mesh': 'mesh'}}))
    project = tmp_path / 'snowcast.json'
    project.write_text(json.dumps({
        'version': 2, 'id': 'west',
        'model': {'config': 'model.json'},
        'forcing': {'archive': 'hrdps', 'index': 'metadata/metdata-hrdps.json'},
    }))
    return project


def change(project_file, callback):
    raw = json.loads(project_file.read_text())
    callback(raw)
    project_file.write_text(json.dumps(raw))


def test_prepare_creates_link_and_index_then_stages_independent_snapshot(project_file, monkeypatch):
    project = load_project(project_file); domain = project
    archive = domain.forcing['archive']; index = domain.forcing['index']
    source_bytes = next(archive.glob('*.nc')).read_bytes()
    monkeypatch.chdir(project_file.parent.parent)
    assert main(['validate', str(project_file)]) == 0
    assert not index.exists() and not project.work.exists()
    assert main(['prepare', str(project_file)]) == 0
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
    assert main(['met-update', str(project_file)]) == 0
    assert len(json.loads(index.read_text())) == 2
    assert json.loads(snapshot.read_text()) == metadata  # met-update leaves a staged run alone.
    assert main(['prepare', str(project_file)]) == 0
    assert len(json.loads(snapshot.read_text())) == 2
    assert link.lstat().st_ino == inode  # Repeated preparation keeps the correct link.


def test_incremental_update_preserves_existing_metadata_and_reads_only_new_files(project_file, monkeypatch):
    domain = load_project(project_file)
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


def test_concurrent_projects_share_canonical_index_lock(project_file):
    project = load_project(project_file)
    archive = project.forcing['archive']
    index = project.forcing['index']
    daily_file(archive, '2026-11-10')
    alias = project_file.parent / 'index-alias.json'
    alias.symlink_to(index)
    other = clone_project(project_file, 'arctic')
    change(other, lambda r: r.update(forcing={'archive': str(archive), 'index': str(alias)}))

    def run(filename):
        return subprocess.run([sys.executable, '-m', 'snowcast_runner', 'met-update', str(filename)],
                              capture_output=True, text=True, timeout=15)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [project_file, other]))
    assert [r.returncode for r in results] == [0, 0], [r.stderr for r in results]
    assert sorted(json.loads(r.stdout)['added'] for r in results) == [0, 2]
    assert len(json.loads(index.read_text())) == 2
    assert alias.is_symlink()
    for domain in (project, load_project(other)):
        assert (domain.work / 'met' / 'archive').resolve() == archive


def test_projects_can_use_separate_archives_and_indices(project_file):
    arctic_archive = project_file.parent / 'arctic-forcing'
    daily_file(arctic_archive, '2026-11-07')
    other = clone_project(project_file, 'arctic')
    change(other, lambda r: r.update(forcing={'archive': str(arctic_archive), 'index': 'metadata/arctic.json'}))
    for filename in (project_file, other):
        assert main(['prepare', str(filename)]) == 0
    snapshots = [json.loads((load_project(p).work / 'met' / 'index.json').read_text()) for p in (project_file, other)]
    assert [rows[0]['end_time'] for rows in snapshots] == ['20261109T230000', '20261107T230000']
    assert len({rows[0]['file_name'] for rows in snapshots}) == 2


def test_different_project_archives_cannot_accidentally_share_an_index(project_file, capsys):
    assert main(['met-update', str(project_file)]) == 0
    index = load_project(project_file).forcing['index']
    before = index.read_bytes()
    other = clone_project(project_file, 'arctic')
    archive = other.parent / 'arctic-forcing'
    daily_file(archive, '2026-11-08')
    change(other, lambda r: r['forcing'].update(archive=str(archive)))
    assert main(['met-update', str(other)]) == 1
    assert 'different archive' in capsys.readouterr().err
    assert index.read_bytes() == before


def test_run_updates_met_before_deciding_model_is_up_to_date(project_file):
    fake = project_file.parent / 'model.py'
    fake.write_text('import json, pathlib, sys\nc=json.load(open(sys.argv[1]))\n'
                    'rows=json.load(open(c["forcing"]["file"]))\n'
                    'assert rows[-1]["end_time"] == "20261110T230000"\n'
                    'pathlib.Path(c["output"]["output_dir"], "clean_exit").touch()\n')
    change(project_file, lambda r: r['model'].update(command=[sys.executable, str(fake), '{config}']))
    assert main(['prepare', str(project_file)]) == 0
    domain = load_project(project_file)
    checkpoints = domain.work / 'chm' / 'output' / 'checkpoint'
    checkpoints.mkdir()
    (checkpoints / 'checkpoint_20261109T230000.np1.json').write_text('{}')
    daily_file(domain.forcing['archive'], '2026-11-10')
    assert main(['run', str(project_file), '--no-postprocess']) == 0
    assert json.loads((domain.work / 'status.json').read_text())['state'] == 'completed'


def test_met_update_does_not_require_model_inputs(project_file):
    (project_file.parent / 'model.json').unlink()
    assert main(['met-update', str(project_file)]) == 0
    assert not (load_project(project_file).work / 'chm').exists()


@pytest.mark.parametrize('kind', ['corrupt', 'no-time', 'empty-time', 'numeric-time'])
def test_bad_new_file_preserves_previous_index(project_file, kind):
    domain = load_project(project_file)
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
    assert main(['met-update', str(project_file)]) == 1
    assert index.read_bytes() == before
    assert json.loads((domain.work / 'status.json').read_text())['state'] == 'failed'


@pytest.mark.parametrize('kind', ['directory', 'other-link', 'broken-link', 'met-link'])
def test_prepare_does_not_replace_conflicting_met_paths(project_file, kind):
    domain = load_project(project_file)
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
    assert main(['prepare', str(project_file)]) == 1
    assert not domain.forcing['index'].exists()
    assert not (domain.forcing['archive'] / 'index.json').exists()


def test_empty_archive_does_not_publish_empty_index(project_file):
    domain = load_project(project_file)
    next(domain.forcing['archive'].glob('*.nc')).unlink()
    assert main(['met-update', str(project_file)]) == 1
    assert not domain.forcing['index'].exists()


@pytest.mark.parametrize('forcing', [
    {'archive': 'absent', 'index': 'metadata/index.json'},
    {'archive': 'mesh', 'index': 'metadata/index.json'},
    {'archive': 'work/archive', 'index': 'metadata/index.json'},
    {'archive': 'hrdps', 'index': 'work/index.json'},
    {'archive': 'hrdps', 'index': 'hrdps'},
])
def test_forcing_validation_is_read_only_and_rejects_invalid_paths(project_file, forcing):
    change(project_file, lambda r: r.update(forcing=forcing))
    assert main(['validate', str(project_file)]) == 1
    assert not (project_file.parent / 'work').exists()
    assert not (project_file.parent / 'metadata').exists()


def test_index_only_project_can_consume_shared_metadata(project_file):
    domain = load_project(project_file)
    update_index(domain.forcing['archive'], domain.forcing['index'])
    other = clone_project(project_file, 'arctic')
    change(other, lambda r: r['forcing'].update(archive=None))
    assert main(['prepare', str(other)]) == 0
    arctic = load_project(other)
    assert not (arctic.work / 'met' / 'archive').exists()
    assert main(['met-update', str(other)]) == 1


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


def test_absolute_archives_and_project_start_dates_use_local_metadata(project_file, monkeypatch):
    archive = project_file.parent / 'external-archive'
    arctic = project_file.parent / 'arctic-forcing'
    daily_file(archive, '2026-09-01')
    daily_file(arctic, '2026-10-01')
    for folder in (archive, arctic):
        (folder / '20250831.nc').write_text('old unreadable NetCDF must not be opened')
        (folder / '20260831.nc').write_text('outside the requested period')
        (folder / '20260830.nc').symlink_to('20260830.nc')  # Must skip before resolving old paths.
    (arctic / '20260930.nc').write_text('before the domain-specific start date')
    change(project_file, lambda r: r.update(forcing={'archive': str(archive)}))
    change(project_file, lambda r: r['model'].update(start_date='2026-09-01'))
    other = clone_project(project_file, 'arctic')
    change(other, lambda r: r.update(forcing={'archive': str(arctic)}))
    change(other, lambda r: r['model'].update(start_date='2026-10-01'))
    monkeypatch.chdir(project_file.parent.parent)
    assert main(['validate', str(project_file)]) == 0
    project = load_project(project_file)
    assert not project.work.exists()
    opened = []
    real_open = xr.open_dataset

    def tracked_open(filename, *args, **kwargs):
        opened.append(Path(filename))
        return real_open(filename, *args, **kwargs)

    monkeypatch.setattr(xr, 'open_dataset', tracked_open)
    for filename in (project_file, other):
        assert main(['prepare', str(filename)]) == 0
    assert opened == [archive / '20260901.nc', archive / '20261109.nc', arctic / '20261001.nc']
    for domain in (project, load_project(other)):
        index = domain.forcing['index']
        assert index == domain.work / 'met' / 'metadata.json'
        assert index.is_file()
        config = json.loads((domain.work / 'chm' / 'config.json').read_text())
        assert config['option']['startdate'] == domain.model['start_date'].replace('-', '') + 'T000000'
        assert config['forcing']['file'] == str(domain.work / 'met' / 'index.json')
    assert not (project_file.parent / 'metadata').exists()  # No shared index path is needed.
    before = list(opened)
    daily_file(archive, '2026-11-10')
    assert main(['met-update', str(project_file)]) == 0
    assert opened == before + [archive / '20261110.nc']


def test_existing_index_is_filtered_before_checking_old_missing_files(project_file):
    domain = load_project(project_file)
    index = domain.forcing['index']
    index.parent.mkdir()
    current = str(domain.forcing['archive'] / '20261109.nc')
    old = project_file.parent / 'missing-old-file.nc'
    old.symlink_to(old.name)  # Even resolving this old path would fail.
    rows = [
        {'start_time': '20260831T000000', 'end_time': '20260831T230000', 'file_name': str(old)},
        {'start_time': '20260831T230000', 'end_time': '20260901T010000', 'file_name': current},
        {'start_time': '20261109T000000', 'end_time': '20261109T230000', 'file_name': current},
    ]
    index.write_text(json.dumps(rows))
    original = index.read_bytes()
    change(project_file, lambda r: r['forcing'].update(archive=None))
    change(project_file, lambda r: r['model'].update(start_date='2026-09-01'))
    assert main(['prepare', str(project_file)]) == 0
    snapshot = json.loads((domain.work / 'met' / 'index.json').read_text())
    assert snapshot == rows[1:]  # Include files whose actual interval crosses the cutoff.
    assert index.read_bytes() == original


def test_shared_index_keeps_history_for_projects_with_different_start_dates(project_file):
    domain = load_project(project_file)
    archive, index = domain.forcing['archive'], domain.forcing['index']
    daily_file(archive, '2026-09-01')
    daily_file(archive, '2026-10-01')
    change(project_file, lambda r: r['model'].update(start_date='2026-09-01'))
    other = clone_project(project_file, 'arctic')
    change(other, lambda r: r['model'].update(start_date='2026-11-01'))
    assert main(['prepare', str(project_file)]) == 0
    before = index.read_bytes()
    assert main(['prepare', str(other)]) == 0
    project = load_project(project_file)
    assert index.read_bytes() == before
    assert [len(json.loads((p.work / 'met' / 'index.json').read_text())) for p in (project, load_project(other))] == [3, 1]


def test_moving_start_date_earlier_backfills_previously_skipped_files(project_file):
    archive = project_file.parent / 'external-archive'
    daily_file(archive, '2026-08-31')
    change(project_file, lambda r: r.update(forcing={'archive': str(archive)}))
    change(project_file, lambda r: r['model'].update(start_date='2026-09-01'))
    assert main(['met-update', str(project_file)]) == 0
    index = load_project(project_file).forcing['index']
    assert len(json.loads(index.read_text())) == 1
    change(project_file, lambda r: r['model'].update(start_date='2026-08-01'))
    assert main(['met-update', str(project_file)]) == 0
    assert len(json.loads(index.read_text())) == 2


def test_no_files_in_requested_period_fails_without_reading_old_netcdfs(project_file, monkeypatch, capsys):
    archive = project_file.parent / 'external-archive'
    change(project_file, lambda r: r.update(forcing={'archive': str(archive)}))
    change(project_file, lambda r: r['model'].update(start_date='2026-12-01'))

    def unexpected_open(*args, **kwargs):
        pytest.fail('Out-of-period daily files must not be opened')

    monkeypatch.setattr(xr, 'open_dataset', unexpected_open)
    assert main(['met-update', str(project_file)]) == 1
    assert 'No forcing available on or after 2026-12-01' in capsys.readouterr().err
    assert not load_project(project_file).forcing['index'].exists()


def test_undated_files_use_actual_intervals_for_start_date_filter(project_file):
    archive = project_file.parent / 'external-archive'
    old = daily_file(archive, '2026-08-31')
    old.rename(archive / 'old-data.nc')
    span = archive / 'spanning-data.nc'
    xr.Dataset(coords={'time': np.array(['2026-08-31T23:00', '2026-09-01T00:00'], dtype='datetime64[ns]')}).to_netcdf(span)
    change(project_file, lambda r: r.update(forcing={'archive': str(archive)}))
    change(project_file, lambda r: r['model'].update(start_date='2026-09-01'))
    assert main(['prepare', str(project_file)]) == 0
    domain = load_project(project_file)
    records = json.loads((domain.work / 'met' / 'index.json').read_text())
    assert {Path(row['file_name']).name for row in records} == {'spanning-data.nc', '20261109.nc'}


def test_legacy_updater_also_honours_start_date(project_file, monkeypatch):
    met = project_file.parent / 'met'
    met.mkdir()
    archive = project_file.parent / 'external-archive'
    (archive / '20260831.nc').write_text('old invalid NetCDF')
    (met / 'hrdps').symlink_to(archive, target_is_directory=True)
    monkeypatch.chdir(project_file.parent)
    result = update_metdata_json({'start_date': '2026-09-01'})
    assert result['added'] == 1 and result['skipped_before_start'] == 1


def test_managed_metadata_cannot_redirect_writes_outside_domain(project_file):
    archive = project_file.parent / 'external-archive'
    change(project_file, lambda r: r.update(forcing={'archive': str(archive)}))
    index = load_project(project_file).forcing['index']
    index.parent.mkdir(parents=True)
    elsewhere = project_file.parent / 'user-file.json'
    elsewhere.write_text('[]')
    index.symlink_to(elsewhere)
    assert main(['met-update', str(project_file)]) == 1
    assert elsewhere.read_text() == '[]' and index.is_symlink()


def test_archive_update_preserves_old_records_without_resolving_their_paths(project_file, monkeypatch):
    project = load_project(project_file)
    index = project.forcing['index']
    index.parent.mkdir()
    old = project.file.parent / 'old-loop.nc'
    old.symlink_to(old.name)
    rows = [
        {'start_time': '20250831T000000', 'end_time': '20250831T230000', 'file_name': str(old)},
        {'start_time': '20261109T000000', 'end_time': '20261109T230000',
         'file_name': str(project.forcing['archive'] / '20261109.nc')},
    ]
    index.write_text(json.dumps(rows))
    before = index.read_bytes()
    change(project_file, lambda r: r['model'].update(start_date='2026-09-01'))
    monkeypatch.setattr(xr, 'open_dataset', lambda *a, **k: pytest.fail('Existing metadata must be used'))
    assert main(['prepare', str(project_file)]) == 0
    assert index.read_bytes() == before
    assert json.loads((project.work / 'met/index.json').read_text()) == rows[1:]


def test_indexed_undated_old_files_are_not_reopened(project_file, monkeypatch):
    project = load_project(project_file)
    old = daily_file(project.forcing['archive'], '2026-08-31')
    old.rename(old.with_name('old-data.nc'))
    update_index(project.forcing['archive'], project.forcing['index'])
    monkeypatch.setattr(xr, 'open_dataset', lambda *a, **k: pytest.fail('Indexed NetCDF must not be reopened'))
    result = update_index(project.forcing['archive'], project.forcing['index'], start_date='2026-09-01')
    assert result['added'] == 0 and result['active_files'] == 1
