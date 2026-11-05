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
    uploader.upload(tmp_path, 'user@example.org', '/srv/snowcast/data')
    assert [c[0] for c in calls] == ['ssh', 'rsync', 'rsync', 'ssh']
    assert calls[-1][-1].startswith('mv -- ')


def test_failed_asset_transfer_never_switches_catalogue(tmp_path, monkeypatch):
    fixture(tmp_path)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == 'rsync':
            raise subprocess.CalledProcessError(23, command)
    monkeypatch.setattr(uploader.subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        uploader.upload(tmp_path, 'user@example.org', '/srv/snowcast/data')
    assert len(calls) == 2
