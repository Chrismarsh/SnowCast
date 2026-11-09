import importlib.util
import json
from pathlib import Path
import shlex
import subprocess

import pytest

spec = importlib.util.spec_from_file_location('uploader', Path(__file__).parents[1] / 'webupload/v3.py')
uploader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uploader)


@pytest.fixture(autouse=True)
def retry_delays(monkeypatch):
    delays = []
    monkeypatch.setattr(uploader.time, 'sleep', delays.append)
    return delays


def fixture(folder):
    asset = folder / 'cogs/swe/fixture.tif'
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b'fixture')
    catalogue = json.dumps({'variables': [{'assets': [{'path': 'cogs/swe/fixture.tif'}]}]}).encode()
    (folder / 'catalog.json').write_bytes(catalogue)
    return catalogue


def test_upload_uses_one_snapshot_and_publishes_catalogue_last(tmp_path, monkeypatch):
    original = fixture(tmp_path)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == 'rsync' and any(s.startswith('--files-from=') for s in command):
            (tmp_path / 'catalog.json').write_text('{}')  # Concurrent local publication.
        elif command[0] == 'rsync':
            assert Path(command[-2]).read_bytes() == original
    monkeypatch.setattr(uploader.subprocess, 'run', run)
    refreshed = []
    def refresh(host, directory):
        assert calls[-1][0] == 'ssh' and '/catalog.json' in calls[-1][-1]
        refreshed.append((host, directory))
    monkeypatch.setattr(uploader, 'upload_download_index', refresh)
    uploader.upload(tmp_path, 'user@example.org', '/srv/snowcast/data')
    assert [c[0] for c in calls] == ['ssh', 'rsync', 'rsync', 'ssh']
    assert calls[-1][-1].startswith('mv -- ')
    assert refreshed == [('user@example.org', '/srv/snowcast')]


def test_failed_asset_transfer_never_switches_catalogue(tmp_path, monkeypatch, retry_delays):
    fixture(tmp_path)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == 'rsync':
            raise subprocess.CalledProcessError(23, command)
    monkeypatch.setattr(uploader.subprocess, 'run', run)
    monkeypatch.setattr(uploader, 'upload_download_index', lambda *_: pytest.fail('Index must follow successful COG publication'))
    with pytest.raises(subprocess.CalledProcessError):
        uploader.upload(tmp_path, 'user@example.org', '/srv/snowcast/data')
    assert [c[0] for c in calls] == ['ssh'] + ['rsync'] * 10
    assert retry_delays == [30 * 2**i for i in range(9)]


def test_download_index_upload_publishes_only_after_a_complete_transfer(tmp_path, monkeypatch):
    content = b'{"version":1,"files":[{"name":"swe-0.001x0.001_20261107T230000.tiff"}]}'
    monkeypatch.setattr(uploader, '_build_download_index', lambda path: path.write_bytes(content))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == 'rsync':
            assert Path(command[-2]).read_bytes() == content
            assert command[-1].startswith('user@example.org:/srv/snowcast/.download-index-')
    monkeypatch.setattr(uploader.subprocess, 'run', run)
    uploader.upload_download_index('user@example.org', '/srv/snowcast')
    assert [c[0] for c in calls] == ['ssh', 'rsync', 'ssh']
    assert calls[-1][-1].endswith(' /srv/snowcast/download-index.json')


def test_failed_index_refresh_never_touches_remote_index(monkeypatch):
    def fail(path):
        raise ValueError('The directory contained no recognized TIFF files')
    monkeypatch.setattr(uploader, '_build_download_index', fail)
    monkeypatch.setattr(uploader.subprocess, 'run', lambda *_a, **_kw: pytest.fail('No remote writes on failed refresh'))
    with pytest.raises(ValueError, match='no recognized TIFF'):
        uploader.upload_download_index('user@example.org', '/srv/snowcast')


def test_failed_index_transfer_never_replaces_live_index(monkeypatch, retry_delays):
    monkeypatch.setattr(uploader, '_build_download_index', lambda path: path.write_text('{}'))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == 'rsync':
            raise subprocess.CalledProcessError(23, command)
    monkeypatch.setattr(uploader.subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        uploader.upload_download_index('user@example.org', '/srv/snowcast')
    assert [c[0] for c in calls] == ['ssh'] + ['rsync'] * 10
    assert retry_delays == [30 * 2**i for i in range(9)]


@pytest.mark.parametrize('failed_stage', [
    'data-directory', 'assets', 'catalog-transfer', 'catalog-publish',
    'index-directory', 'index-transfer', 'index-publish',
])
def test_upload_recovers_from_a_blip_at_each_remote_step(tmp_path, monkeypatch, retry_delays, failed_stage):
    original = fixture(tmp_path)
    index = b'{"version":1,"files":[]}'
    completed = []
    failed = False
    builds = []

    def build(path):
        assert 'catalog-publish' in completed
        builds.append(path)
        path.write_bytes(index)

    def run(command, **kwargs):
        nonlocal failed
        assert kwargs['check'] is True
        if command[0] == 'ssh' and command[-1].startswith('mkdir '):
            stage = 'data-directory' if command[-1].endswith('/data') else 'index-directory'
        elif command[0] == 'rsync' and any(s.startswith('--files-from=') for s in command):
            stage = 'assets'
        else:
            kind = 'index' if '.download-index-' in command[-1] else 'catalog'
            stage = kind + ('-transfer' if command[0] == 'rsync' else '-publish')
            if command[0] == 'rsync':
                assert Path(command[-2]).read_bytes() == (original if kind == 'catalog' else index)
            if kind == 'catalog':
                assert 'assets' in completed
        if stage == failed_stage and not failed:
            failed = True
            (tmp_path / 'catalog.json').write_text('{}')  # A newer local catalogue must not replace this snapshot.
            raise subprocess.CalledProcessError(255 if command[0] == 'ssh' else 12, command)
        completed.append(stage)

    monkeypatch.setattr(uploader, '_build_download_index', build)
    monkeypatch.setattr(uploader.subprocess, 'run', run)
    uploader.upload(tmp_path, 'user@example.org', '/srv/snowcast/data')
    assert failed
    assert completed[-1] == 'index-publish'
    assert retry_delays == [30]
    assert len(builds) == 1


@pytest.mark.parametrize('target', ['catalog.json', 'download-index.json'])
def test_disconnect_after_remote_rename_restages_the_snapshot(tmp_path, monkeypatch, retry_delays, target):
    original = fixture(tmp_path)
    index = b'{"version":1,"files":[]}'
    remote = {}
    publications = []
    failed = False
    monkeypatch.setattr(uploader, '_build_download_index', lambda path: path.write_bytes(index))

    def run(command, **kwargs):
        nonlocal failed
        if command[0] == 'rsync' and not any(s.startswith('--files-from=') for s in command):
            remote[command[-1].split(':', 1)[1]] = Path(command[-2]).read_bytes()
        elif command[0] == 'ssh' and command[-1].startswith('mv -- '):
            _, _, source, destination = shlex.split(command[-1])
            # mv consumes its source even if the client never gets an acknowledgement.
            remote[destination] = remote.pop(source)
            publications.append(destination)
            if destination.endswith('/' + target) and not failed:
                failed = True
                raise subprocess.CalledProcessError(255, command)

    monkeypatch.setattr(uploader.subprocess, 'run', run)
    uploader.upload(tmp_path, 'user@example.org', '/srv/snowcast/data')
    assert remote['/srv/snowcast/data/catalog.json'] == original
    assert remote['/srv/snowcast/download-index.json'] == index
    assert sum(path.endswith('/' + target) for path in publications) == 2
    assert retry_delays == [30]


def test_index_failure_does_not_fail_successful_cog_upload(tmp_path, monkeypatch, capsys):
    fixture(tmp_path)
    calls = []
    monkeypatch.setattr(uploader.subprocess, 'run', lambda command, **kwargs: calls.append(command))
    def fail(host, directory):
        assert directory == '/srv/custom-ui'
        raise TimeoutError('Archive unavailable')
    monkeypatch.setattr(uploader, 'upload_download_index', fail)
    uploader.upload(tmp_path, 'user@example.org', '/srv/snowcast/data', '/srv/custom-ui')
    assert calls[-1][-1].endswith('/catalog.json')
    assert 'WARNING: COG catalogue published' in capsys.readouterr().err


def test_downloads_only_cli_needs_no_data_and_never_transfers_cogs(monkeypatch):
    calls = []
    monkeypatch.setattr(uploader, 'upload_download_index', lambda *args: calls.append(args))
    monkeypatch.setattr(uploader, 'upload', lambda *_: pytest.fail('No COG upload'))
    uploader.main(['--downloads-only', '--host', 'user@example.org', '--directory', '/srv/snowcast/data'])
    assert calls == [('user@example.org', '/srv/snowcast')]
    with pytest.raises(SystemExit) as error:
        uploader.main(['--host', 'user@example.org', '--directory', '/srv/snowcast/data'])
    assert error.value.code == 2
