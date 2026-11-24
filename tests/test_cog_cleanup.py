import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from snowcast_runner import cog_store as store


def asset(root, number, variable='swe'):
    relative = f'cogs/{variable}/20261109T230000-{number:020x}-float32-v1.tif'
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(100))
    return relative


def catalogue(paths, generated='2026-11-09T12:00:00Z'):
    return {'version': 1, 'generated_at': generated,
            'variables': [{'id': 'swe', 'assets': [{'path': p, 'bytes': 100} for p in paths]}]}


def test_cleanup_ages_from_loss_of_references_and_keeps_current_files(tmp_path):
    old, new = asset(tmp_path, 1), asset(tmp_path, 2)
    os.utime(tmp_path / old, (1, 1))
    store.atomic_json(tmp_path / 'catalog.json', catalogue([new]))
    with store.store_lock(tmp_path):
        store.cleanup_locked(tmp_path, now=200000)
        assert (tmp_path / old).exists()
        store.cleanup_locked(tmp_path, now=200000 + 48 * 3600 - 1)
        assert (tmp_path / old).exists()
        result = store.cleanup_locked(tmp_path, now=200000 + 48 * 3600)
    assert result['removable_files'] == [old]
    assert not (tmp_path / old).exists() and (tmp_path / new).exists()


def test_referencing_again_resets_the_grace_period(tmp_path):
    a, b = asset(tmp_path, 1), asset(tmp_path, 2)
    store.atomic_json(tmp_path / 'catalog.json', catalogue([b]))
    store.cleanup_locked(tmp_path, now=200000)
    store.atomic_json(tmp_path / 'catalog.json', catalogue([a, b]))
    store.cleanup_locked(tmp_path, now=300000)
    store.atomic_json(tmp_path / 'catalog.json', catalogue([b]))
    store.cleanup_locked(tmp_path, now=400000)
    assert (tmp_path / a).exists()
    assert json.loads((tmp_path / '.cog-cleanup.json').read_text())['unreferenced'][a] == 400000


def test_upload_pin_protects_old_files_and_next_attempt_replaces_a_stale_pin(tmp_path):
    a, b, c = (asset(tmp_path, i) for i in (1, 2, 3))
    store.atomic_json(tmp_path / 'catalog.json', catalogue([c]))
    store.cleanup_locked(tmp_path, now=200000)
    token = 'a' * 32
    store.remote_action('pin', tmp_path, token, json.dumps(catalogue([a])))
    store.cleanup_locked(tmp_path, now=400000)
    assert (tmp_path / a).exists() and not (tmp_path / b).exists()
    store.remote_action('pin', tmp_path, token, json.dumps(catalogue([c])))
    store.cleanup_locked(tmp_path, now=500000)
    assert (tmp_path / a).exists()  # Starts a fresh grace period after unpinning.


def test_dry_run_changes_neither_files_nor_cleanup_state(tmp_path):
    a, b = asset(tmp_path, 1), asset(tmp_path, 2)
    store.atomic_json(tmp_path / 'catalog.json', catalogue([b]))
    store.cleanup_locked(tmp_path, now=200000)
    state = (tmp_path / '.cog-cleanup.json').read_bytes()
    result = store.cleanup_locked(tmp_path, now=400000, dry_run=True)
    assert result['removable_files'] == [a] and (tmp_path / a).exists()
    assert (tmp_path / '.cog-cleanup.json').read_bytes() == state


@pytest.mark.parametrize('corrupt', ['catalogue', 'state', 'pin', 'missing_asset'])
def test_invalid_state_fails_closed_before_deleting_anything(tmp_path, corrupt):
    a, b = asset(tmp_path, 1), asset(tmp_path, 2)
    store.atomic_json(tmp_path / 'catalog.json', catalogue([b]))
    store.cleanup_locked(tmp_path, now=200000)
    if corrupt == 'catalogue':
        (tmp_path / 'catalog.json').write_text('{}')
    elif corrupt == 'state':
        (tmp_path / '.cog-cleanup.json').write_text('invalid')
    elif corrupt == 'pin':
        (tmp_path / '.uploads').mkdir()
        (tmp_path / '.uploads/bad.json').write_text('invalid')
    else:
        (tmp_path / b).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        store.cleanup_locked(tmp_path, now=400000)
    assert (tmp_path / a).exists()


def test_cleanup_ignores_unmanaged_files_and_symlinks(tmp_path):
    current = asset(tmp_path, 1)
    store.atomic_json(tmp_path / 'catalog.json', catalogue([current]))
    original = tmp_path / 'original.tiff'; original.write_bytes(b'original')
    unmanaged = tmp_path / 'cogs/swe/keep.tif'; unmanaged.write_bytes(b'other')
    linked = tmp_path / 'cogs/swe/20261109T230000-00000000000000000002-float32-v1.tif'
    linked.symlink_to(original)
    store.cleanup_locked(tmp_path, now=200000)
    store.cleanup_locked(tmp_path, now=400000)
    assert original.exists() and unmanaged.exists() and linked.is_symlink()


def test_remote_commit_verifies_files_and_prevents_older_upload_rollback(tmp_path):
    a, b = asset(tmp_path, 1), asset(tmp_path, 2)
    old, new = catalogue([a]), catalogue([b], '2026-11-09T13:00:00Z')
    store.remote_action('pin', tmp_path, 'a' * 32, json.dumps(old))
    store.remote_action('pin', tmp_path, 'b' * 32, json.dumps(new))
    store.remote_action('commit', tmp_path, 'b' * 32)
    store.remote_action('commit', tmp_path, 'a' * 32)
    assert json.loads((tmp_path / 'catalog.json').read_text()) == new
    missing = catalogue(['cogs/swe/missing.tif'], '2026-11-09T14:00:00Z')
    store.remote_action('pin', tmp_path, 'c' * 32, json.dumps(missing))
    with pytest.raises(FileNotFoundError):
        store.remote_action('commit', tmp_path, 'c' * 32)
    assert json.loads((tmp_path / 'catalog.json').read_text()) == new


def test_store_lock_excludes_another_process(tmp_path):
    code = "import fcntl, sys; f=open(sys.argv[1], 'a'); fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)"
    with store.store_lock(tmp_path):
        result = subprocess.run([sys.executable, '-c', code, str(tmp_path / '.publish.lock')], capture_output=True)
        assert result.returncode != 0 and b'BlockingIOError' in result.stderr
    assert subprocess.run([sys.executable, '-c', code, str(tmp_path / '.publish.lock')]).returncode == 0


def test_remote_helper_executes_without_project_or_rasterio_imports(tmp_path):
    current = asset(tmp_path, 1)
    source = Path(store.__file__).read_text()
    pin = subprocess.run([sys.executable, '-I', '-S', '-c', source, 'pin', str(tmp_path), 'a' * 32],
                         input=json.dumps(catalogue([current])).encode(), capture_output=True)
    assert pin.returncode == 0, pin.stderr.decode()
    commit = subprocess.run([sys.executable, '-I', '-S', '-c', source, 'commit', str(tmp_path), 'a' * 32],
                            capture_output=True)
    assert commit.returncode == 0, commit.stderr.decode()
    assert json.loads((tmp_path / 'catalog.json').read_text()) == catalogue([current])


@pytest.mark.parametrize('prefix', ['cogs/swe/./', 'cogs//swe/', './cogs/swe/'])
@pytest.mark.parametrize('reference', ['catalogue', 'pin'])
def test_noncanonical_references_stop_cleanup_without_deleting_files(tmp_path, prefix, reference):
    old, current = asset(tmp_path, 1), asset(tmp_path, 2)
    store.atomic_json(tmp_path / 'catalog.json', catalogue([current]))
    store.cleanup_locked(tmp_path, now=200000)
    state = (tmp_path / '.cog-cleanup.json').read_bytes()
    malformed = catalogue([prefix + Path(old).name])
    target = tmp_path / ('catalog.json' if reference == 'catalogue' else '.uploads/pin.json')
    store.atomic_json(target, malformed)
    with pytest.raises(ValueError, match='Invalid COG path'):
        store.cleanup_locked(tmp_path, now=400000)
    assert (tmp_path / old).exists() and (tmp_path / current).exists()
    assert (tmp_path / '.cog-cleanup.json').read_bytes() == state
    with pytest.raises(ValueError, match='Invalid COG path'):
        store.remote_action('pin', tmp_path, 'a' * 32, json.dumps(malformed))


def test_same_version_with_different_contents_cannot_replace_the_catalogue(tmp_path):
    a, b = asset(tmp_path, 1), asset(tmp_path, 2)
    old, new = catalogue([a]), catalogue([b])
    store.remote_action('pin', tmp_path, 'a' * 32, json.dumps(old))
    store.remote_action('pin', tmp_path, 'b' * 32, json.dumps(new))
    store.remote_action('commit', tmp_path, 'b' * 32)
    before = (tmp_path / 'catalog.json').read_bytes()
    with pytest.raises(ValueError, match='Conflicting catalogue'):
        store.remote_action('commit', tmp_path, 'a' * 32)
    assert (tmp_path / 'catalog.json').read_bytes() == before
    store.remote_action('pin', tmp_path, 'b' * 32, json.dumps(new, sort_keys=True))
    store.remote_action('commit', tmp_path, 'b' * 32)  # Semantic equality permits retry.
    assert (tmp_path / 'catalog.json').read_bytes() == before


def test_remote_publication_repairs_umask_permissions_before_switching(tmp_path, monkeypatch):
    root = tmp_path / 'published'
    mask = os.umask(0o077)
    try:
        current = asset(root, 1)
        store.remote_action('pin', root, 'a' * 32, json.dumps(catalogue([current])))
        original = store.atomic_json
        def checked(path, value):
            if path.name == 'catalog.json':
                for directory in [root, root / 'cogs', root / 'cogs/swe']:
                    assert directory.stat().st_mode & 0o777 == 0o755
                assert (root / current).stat().st_mode & 0o777 == 0o644
            original(path, value)
        monkeypatch.setattr(store, 'atomic_json', checked)
        store.remote_action('commit', root, 'a' * 32)
    finally:
        os.umask(mask)
    assert (root / 'catalog.json').stat().st_mode & 0o777 == 0o644


def test_symlink_reference_cannot_hide_the_live_target_from_cleanup(tmp_path):
    old, current = asset(tmp_path, 1), asset(tmp_path, 2)
    store.atomic_json(tmp_path / 'catalog.json', catalogue([current]))
    store.cleanup_locked(tmp_path, now=200000)
    alias = tmp_path / 'cogs/swe/alias.tif'; alias.symlink_to(tmp_path / old)
    store.atomic_json(tmp_path / 'catalog.json', catalogue(['cogs/swe/alias.tif']))
    with pytest.raises(ValueError, match='symlinks'):
        store.cleanup_locked(tmp_path, now=400000)
    assert (tmp_path / old).exists()


def test_permission_failure_cannot_switch_the_remote_catalogue(tmp_path, monkeypatch):
    a, b = asset(tmp_path, 1), asset(tmp_path, 2)
    store.atomic_json(tmp_path / 'catalog.json', catalogue([a]))
    store.remote_action('pin', tmp_path, 'a' * 32, json.dumps(catalogue([b], '2026-11-09T13:00:00Z')))
    original = Path.chmod
    def chmod(path, mode, **kwargs):
        if path == tmp_path / b:
            raise PermissionError('Unable to make asset public')
        return original(path, mode, **kwargs)
    monkeypatch.setattr(Path, 'chmod', chmod)
    with pytest.raises(PermissionError):
        store.remote_action('commit', tmp_path, 'a' * 32)
    assert json.loads((tmp_path / 'catalog.json').read_text()) == catalogue([a])
