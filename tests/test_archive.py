import json
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest

from snowcast_runner.archive import archive_project, download_index, inventory, S3
from snowcast_runner.cli import main
from snowcast_runner.project import load_project
from snowcast_runner.site_config import load_site, configure, publish_selected
from test_project_runner import project_file, raster, change


def configure_archive(project_file, tmp_path, **options):
    destination = {'id': 'hpfx', 'backend': 'local', 'directory': str(tmp_path / 'archive'),
                   'public_url': 'https://archive.example/west/', **options}
    change(project_file, lambda raw: raw.update(archive={'destinations': [destination]}))
    project = load_project(project_file)
    raster(project.work / 'postprocess/archive_tiff', stamp='20250901T230000')
    raster(project.work / 'postprocess/tiff')
    return project


def test_local_archive_keeps_history_and_revisions_without_publishing(project_file, tmp_path):
    project = configure_archive(project_file, tmp_path)
    current = project.work / 'postprocess/tiff'
    old = raster(project.work / 'postprocess/archive_tiff')
    old.write_bytes(b'old revision')
    sidecar = current / 'swe-0.001x0.001_20261109T230000.tiff.aux.xml'
    sidecar.write_text('sidecar')
    assert main(['archive', str(project_file)]) == 0
    target = tmp_path / 'archive'
    assert (target / 'tiff' / old.name).read_bytes() == (current / old.name).read_bytes()
    assert (target / 'tiff' / sidecar.name).read_text() == 'sidecar'
    assert len(download_index(project)['sources'][0]['files']) == 2
    assert not (target / 'site.json').exists()
    # Archived dates survive removal from local storage and a second upload.
    (project.work / 'postprocess/archive_tiff' / 'swe-0.001x0.001_20250901T230000.tiff').unlink()
    archive_project(project)
    assert len(json.loads((target / 'archive-index.json').read_text())['sources'][0]['files']) == 2
    # Revisions with the same byte count and preserved mtime are still transferred.
    import os
    file = current / old.name
    stat = file.stat(); file.write_bytes(b'x' * stat.st_size)
    os.utime(file, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    archive_project(project)
    assert (target / 'tiff' / file.name).read_bytes() == file.read_bytes()


def test_dry_run_and_selection_never_contact_backends(project_file, tmp_path, monkeypatch):
    project = configure_archive(project_file, tmp_path)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('unexpected remote command'))
    archive_project(project, dry_run=True)
    assert not (tmp_path / 'archive').exists()
    assert not (project.work / 'archive').exists()
    with pytest.raises(ValueError, match='Unknown'):
        archive_project(project, selected=['absent'])
    assert download_index(project)['sources'] == []


def test_mirrors_and_failures_only_expose_completed_destinations(project_file, tmp_path, monkeypatch):
    project = configure_archive(project_file, tmp_path)
    change(project_file, lambda raw: raw['archive']['destinations'].append({
        'id': 'broken', 'backend': 'rsync', 'host': 'hpfx', 'directory': '/archive/west',
        'public_url': 'https://second.example/west/'}))
    project = load_project(project_file)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: (_ for _ in ()).throw(OSError('offline')))
    with pytest.raises(RuntimeError, match='broken: offline'):
        archive_project(project)
    assert [s['id'] for s in download_index(project)['sources']] == ['hpfx']
    before = (project.work / 'archive/hpfx.json').read_bytes()
    from snowcast_runner.archive import Local
    monkeypatch.setattr(Local, 'commit', lambda *a: (_ for _ in ()).throw(OSError('index failed')))
    with pytest.raises(RuntimeError):
        archive_project(project, selected=['hpfx'])
    assert (project.work / 'archive/hpfx.json').read_bytes() == before
    change(project_file, lambda raw: raw['archive']['destinations'][0].update(public_url='https://moved.example/'))
    assert download_index(load_project(project_file))['sources'] == []


def test_rsync_transport_preserves_other_files_and_commits_last(project_file, tmp_path, monkeypatch):
    project = configure_archive(project_file, tmp_path, backend='rsync', host='hpfx')
    actual_run = subprocess.run
    calls = []
    def transport(command, **kwargs):
        calls.append(command)
        if command[0] == 'ssh':
            return actual_run(shlex.split(command[2]), **kwargs)
        assert command[0] == 'rsync' and '--delete' not in command and '--checksum' in command
        shutil.copytree(command[-2], command[-1].split(':', 1)[1], dirs_exist_ok=True)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(subprocess, 'run', transport)
    archive_project(project)
    assert 'commit' in shlex.split(calls[-1][2])
    assert len(json.loads((tmp_path / 'archive/archive-index.json').read_text())['sources'][0]['files']) == 2
    assert len(download_index(project)['sources']) == 1
    # Ownership is checked before a second project can overwrite a shared root.
    change(project_file, lambda raw: raw.update(id='another'))
    other = load_project(project_file)
    from snowcast_runner.archive import Rsync
    with pytest.raises(subprocess.CalledProcessError):
        Rsync(other.archive[0]).claim(other.id, tmp_path)


def test_s3_custom_endpoint_receipt_and_unchanged_skip(project_file, tmp_path, monkeypatch):
    configure_archive(project_file, tmp_path)
    change(project_file, lambda raw: raw.update(archive={'destinations': [{
        'id': 'object-store', 'backend': 's3', 'bucket': 'snowcast-data', 'prefix': 'projects/{project}',
        'endpoint_url': 'https://s3.example', 'profile': 'snowcast', 'region': 'ca-central-1',
        'public_url': 'https://downloads.example/{project}/'}]}))
    project = load_project(project_file)
    calls = []
    def transport(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, '', '')
    monkeypatch.setattr(subprocess, 'run', transport)
    archive_project(project)
    assert all('--endpoint-url' in c and '--profile' in c for c in calls)
    assert '--if-none-match' in calls[0]
    assert any('--recursive' in c for c in calls)
    assert any('s3://snowcast-data/projects/west/archive-index.json' in c for c in calls)
    calls.clear(); archive_project(project)
    assert not any('--recursive' in c for c in calls)
    calls.clear(); archive_project(project, force=True)
    assert any('--recursive' in c for c in calls)
    assert download_index(project)['sources'][0]['url'] == 'https://downloads.example/west/'


def test_s3_ownership_failure_is_not_treated_as_missing(project_file, tmp_path, monkeypatch):
    d = {'bucket': 'snowcast', 'prefix': 'west'}
    monkeypatch.setattr(subprocess, 'run', lambda command, **kw: subprocess.CompletedProcess(command, 1, '', 'AccessDenied'))
    with pytest.raises(RuntimeError, match='AccessDenied'):
        S3(d).claim('west', tmp_path)


@pytest.mark.parametrize('settings', [
    {'backend': 'unknown'}, {'backend': 'local', 'directory': 'work/archive'},
    {'backend': 'rsync', 'host': '-oops', 'directory': '/archive'},
    {'backend': 's3', 'bucket': 'test-bucket', 'prefix': '../west'},
    {'backend': 'local', 'directory': '/tmp/archive', 'public_url': 'javascript:alert(1)'},
    {'backend': 'local', 'directory': '/tmp/archive', 'access_key': 'not-supported'},
])
def test_invalid_json_destinations_are_rejected(project_file, settings):
    change(project_file, lambda raw: raw.update(archive={'destinations': [{'id': 'test', **settings}]}))
    with pytest.raises(ValueError):
        load_project(project_file)


def test_shared_json_resolves_relative_paths_and_project_placeholders(project_file, tmp_path):
    file = tmp_path / 'archives.json'
    file.write_text(json.dumps({'destinations': [{'id': 'local', 'backend': 'local', 'directory': 'backups/{project}'}]}))
    change(project_file, lambda raw: raw.update(archive='../archives.json'))
    project = load_project(project_file)
    assert project.archive[0]['directory'] == str(tmp_path / 'backups/west')


def test_publish_only_reads_receipts_no_archive_upload(project_file, tmp_path, monkeypatch):
    project = configure_archive(project_file, tmp_path)
    archive_project(project)
    site_file = tmp_path / 'site.json'
    site_file.write_text(json.dumps({'version': 1, 'observations': False, 'projects': [str(project_file)], 'staging': 'website'}))
    site = load_site(site_file); configure(site)
    from snowcast_runner.archive import Local
    monkeypatch.setattr(Local, 'transfer', lambda *a: pytest.fail('publish must not archive'))
    publish_selected(site, 'west', remote=False)
    index = json.loads((site.staging / 'data/west/downloads.json').read_text())
    assert index['project']['id'] == 'west' and len(index['sources'][0]['files']) == 2
    assert str(tmp_path) not in json.dumps(index)
    assert 'config_hash' not in json.dumps(index)


def test_ascii_sidecars_and_source_symlinks(project_file, tmp_path):
    project = configure_archive(project_file, tmp_path)
    folder = project.work / 'postprocess/ascii'; folder.mkdir()
    (folder / 'swe_20261109230000.asc').write_text('ncols 1\nnrows 1\nxllcorner -133\nyllcorner 68\ncellsize 0.036\nNODATA_value -9999\n1\n')
    (folder / 'swe_20261109230000.prj').write_text('projection')
    archive_project(project)
    assert (tmp_path / 'archive/asc/swe_20261109230000.prj').read_text() == 'projection'
    change(project_file, lambda raw: raw.setdefault('postprocess', {}).update(ascii={'resolution': 0.1}))
    _, files = inventory(load_project(project_file))
    assert files['asc/swe_20261109230000.asc']['resolution'] == [0.036, 0.036]
    (folder / 't_20261109230000.asc').symlink_to(project_file)
    with pytest.raises(ValueError, match='symlink'):
        inventory(project)


def test_changed_public_url_preserves_history_after_rearchive(project_file, tmp_path):
    project = configure_archive(project_file, tmp_path)
    archive_project(project)
    (project.work / 'postprocess/archive_tiff' / 'swe-0.001x0.001_20250901T230000.tiff').unlink()
    change(project_file, lambda raw: raw['archive']['destinations'][0].update(public_url='https://new.example/west/', name='New name'))
    project = load_project(project_file)
    assert download_index(project)['sources'] == []
    archive_project(project)
    source = download_index(project)['sources'][0]
    assert source['url'] == 'https://new.example/west/' and len(source['files']) == 2


def test_private_destination_stays_out_of_public_index(project_file, tmp_path):
    project = configure_archive(project_file, tmp_path)
    change(project_file, lambda raw: raw['archive']['destinations'][0].pop('public_url'))
    project = load_project(project_file)
    archive_project(project)
    assert (tmp_path / 'archive/archive-index.json').exists()
    assert download_index(project)['sources'] == []


def test_removed_sidecars_and_symlink_targets_preserve_previous_archive(project_file, tmp_path):
    project = configure_archive(project_file, tmp_path)
    sidecar = project.work / 'postprocess/tiff/swe-0.001x0.001_20261109T230000.tiff.aux.xml'
    sidecar.write_text('metadata'); archive_project(project)
    before = (tmp_path / 'archive/archive-index.json').read_bytes()
    sidecar.unlink()
    with pytest.raises(RuntimeError, match='Sidecars removed'):
        archive_project(project)
    assert (tmp_path / 'archive/archive-index.json').read_bytes() == before
    sidecar.write_text('metadata')
    target = tmp_path / 'archive/tiff/swe-0.001x0.001_20261109T230000.tiff'
    target.unlink(); target.symlink_to(project_file)
    with pytest.raises(RuntimeError, match='symlink'):
        archive_project(project, force=True)
    assert json.loads(project_file.read_text())['id'] == 'west'
