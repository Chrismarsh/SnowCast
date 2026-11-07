import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location('uploader', Path(__file__).parents[1] / 'webupload/v3.py')
uploader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uploader)


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


def test_failed_asset_transfer_never_switches_catalogue(tmp_path, monkeypatch):
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
    assert len(calls) == 2


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


def test_failed_index_transfer_never_replaces_live_index(monkeypatch):
    monkeypatch.setattr(uploader, '_build_download_index', lambda path: path.write_text('{}'))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == 'rsync':
            raise subprocess.CalledProcessError(23, command)
    monkeypatch.setattr(uploader.subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        uploader.upload_download_index('user@example.org', '/srv/snowcast')
    assert [c[0] for c in calls] == ['ssh', 'rsync']


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
