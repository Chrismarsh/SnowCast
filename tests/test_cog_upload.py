import json
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest

from postprocess import cog_store
from webupload import v3 as uploader


@pytest.fixture(autouse=True)
def retry_delays(monkeypatch):
    delays = []
    monkeypatch.setattr(uploader.time, 'sleep', delays.append)
    return delays


def fixture(folder):
    asset = folder / 'cogs/swe/fixture.tif'
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b'fixture')
    catalogue = json.dumps({'version': 1, 'generated_at': '2026-11-09T12:00:00Z',
                           'variables': [{'assets': [{'path': 'cogs/swe/fixture.tif', 'bytes': 7}]}]}).encode()
    (folder / 'catalog.json').write_bytes(catalogue)
    return catalogue


class Host:
    """Exercise the real remote publication helper against a separate directory."""
    def __init__(self, local, remote):
        self.local, self.remote = local, remote
        self.events = []
        self.fail_stage = None
        self.failures = 0
        self.after_commit = False
        self.after_index = False
        self.during_transfer = lambda: None

    def run(self, command, **kwargs):
        assert kwargs['check'] is True
        if command[0] == 'ssh':
            args = shlex.split(command[-1])
            if args[:2] == ['python3', '-c']:
                action, directory, token = args[3:]
                self.stage(action)
                cog_store.remote_action(action, self.remote, token, kwargs.get('input'))
                if action == 'commit' and self.after_commit:
                    self.after_commit = False
                    raise subprocess.CalledProcessError(255, command)
            elif args[0] == 'mkdir':
                self.stage('index-directory')
                self.remote.parent.mkdir(parents=True, exist_ok=True)
            elif args[0] == 'mv':
                self.stage('index-publish')
                source, destination = args[-2:]
                (self.remote.parent / Path(source).name).replace(self.remote.parent / Path(destination).name)
                if self.after_index:
                    self.after_index = False
                    raise subprocess.CalledProcessError(255, command)
            else:
                raise AssertionError(command)
        elif any(s.startswith('--files-from=') for s in command):
            self.stage('assets')
            pins = list((self.remote / '.uploads').glob('*.json'))
            assert len(pins) == 1  # Snapshot was protected before bytes move.
            self.during_transfer()
            listing = next(s.split('=', 1)[1] for s in command if s.startswith('--files-from='))
            for path in Path(listing).read_text().splitlines():
                destination = self.remote / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.local / path, destination)
        else:
            self.stage('index-transfer')
            destination = self.remote.parent / Path(command[-1].split(':', 1)[1]).name
            shutil.copy2(command[-2], destination)

    def stage(self, stage):
        self.events.append(stage)
        if stage == self.fail_stage and self.failures:
            self.failures -= 1
            raise subprocess.CalledProcessError(255, [stage])


@pytest.fixture
def host(tmp_path, monkeypatch):
    local, remote = tmp_path / 'local', tmp_path / 'remote/data'
    original = fixture(local)
    value = Host(local, remote)
    value.original = original
    monkeypatch.setattr(uploader.subprocess, 'run', value.run)
    monkeypatch.setattr(uploader, '_build_download_index', lambda path: path.write_text('{"version":1,"files":[]}'))
    return value


def test_upload_protects_one_snapshot_and_switches_catalogue_after_assets(host):
    host.during_transfer = lambda: (host.local / 'catalog.json').write_text('{}')
    uploader.upload(host.local, 'user@example.org', '/srv/data')
    assert json.loads((host.remote / 'catalog.json').read_bytes()) == json.loads(host.original)
    assert host.events == ['pin', 'assets', 'pin', 'commit', 'index-directory', 'index-transfer', 'index-publish']
    assert not list((host.remote / '.uploads').glob('*.json'))
    assert (host.remote / 'cogs/swe/fixture.tif').read_bytes() == b'fixture'


@pytest.mark.parametrize('stage', ['pin', 'assets', 'commit', 'index-directory', 'index-transfer', 'index-publish'])
def test_upload_recovers_from_a_failure_at_each_remote_step(host, retry_delays, stage):
    host.fail_stage, host.failures = stage, 1
    uploader.upload(host.local, 'user@example.org', '/srv/data')
    assert json.loads((host.remote / 'catalog.json').read_bytes()) == json.loads(host.original)
    assert (host.remote.parent / 'download-index.json').is_file()
    assert retry_delays == [30]


def test_disconnect_after_commit_recreates_the_consumed_pin(host, retry_delays):
    host.after_commit = True
    uploader.upload(host.local, 'user@example.org', '/srv/data')
    assert host.events.count('commit') == 2 and host.events.count('pin') == 3
    assert json.loads((host.remote / 'catalog.json').read_bytes()) == json.loads(host.original)
    assert not list((host.remote / '.uploads').glob('*.json'))
    assert retry_delays == [30]


def test_disconnect_after_index_rename_restages_the_index(host, retry_delays):
    host.after_index = True
    uploader.upload(host.local, 'user@example.org', '/srv/data')
    assert host.events.count('index-transfer') == host.events.count('index-publish') == 2
    assert json.loads((host.remote.parent / 'download-index.json').read_text()) == {'version': 1, 'files': []}
    assert retry_delays == [30]


def test_failed_asset_transfer_never_switches_catalogue_or_cleans_remote_files(host, retry_delays):
    host.remote.mkdir(parents=True)
    (host.remote / 'catalog.json').write_text('{"previous": true}')
    host.fail_stage, host.failures = 'assets', 10
    with pytest.raises(subprocess.CalledProcessError):
        uploader.upload(host.local, 'user@example.org', '/srv/data')
    assert (host.remote / 'catalog.json').read_text() == '{"previous": true}'
    assert 'commit' not in host.events and 'index-directory' not in host.events
    assert not list((host.remote / '.uploads').glob('*.json'))
    assert retry_delays == [30 * 2**i for i in range(9)]


def test_upload_holds_the_local_store_lock_during_asset_transfer(host):
    import fcntl
    def check_lock():
        with (host.local / '.publish.lock').open('a') as lock:
            with pytest.raises(BlockingIOError):
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    host.during_transfer = check_lock
    uploader.upload(host.local, 'user@example.org', '/srv/data')


def test_index_failure_does_not_fail_successful_cog_upload(host, monkeypatch, capsys):
    def fail(*args):
        raise TimeoutError('Archive unavailable')
    monkeypatch.setattr(uploader, 'upload_download_index', fail)
    uploader.upload(host.local, 'user@example.org', '/srv/data')
    assert (host.remote / 'catalog.json').is_file()
    assert 'WARNING: COG catalogue published' in capsys.readouterr().err


def test_download_index_refresh_failure_does_not_touch_the_host(monkeypatch):
    def fail(path):
        raise ValueError('No archive files')
    monkeypatch.setattr(uploader, '_build_download_index', fail)
    monkeypatch.setattr(uploader.subprocess, 'run', lambda *a, **k: pytest.fail('Unexpected remote write'))
    with pytest.raises(ValueError):
        uploader.upload_download_index('user@example.org', '/srv/data')


def test_failed_index_transfer_never_replaces_live_index(host, retry_delays):
    host.remote.parent.mkdir(parents=True)
    index = host.remote.parent / 'download-index.json'
    index.write_text('old')
    host.fail_stage, host.failures = 'index-transfer', 10
    with pytest.raises(subprocess.CalledProcessError):
        uploader.upload_download_index('user@example.org', '/srv')
    assert index.read_text() == 'old' and 'index-publish' not in host.events
    assert retry_delays == [30 * 2**i for i in range(9)]


def test_downloads_only_cli_needs_no_data(monkeypatch):
    calls = []
    monkeypatch.setattr(uploader, 'upload_download_index', lambda *args: calls.append(args))
    monkeypatch.setattr(uploader, 'upload', lambda *args: pytest.fail('Unexpected COG upload'))
    uploader.main(['--downloads-only', '--host', 'user@example.org', '--directory', '/srv/data'])
    assert calls == [('user@example.org', '/srv')]
    with pytest.raises(SystemExit):
        uploader.main(['--host', 'user@example.org', '--directory', '/srv/data'])
