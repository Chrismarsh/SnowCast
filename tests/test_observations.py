"""Observation lifecycle uses tiny synthetic NetCDF; never downloads real data."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest

from snowcast_runner import observation_data, observations
from snowcast_runner.cli import main
from snowcast_runner.cog_store import atomic_json, commit_observations
from snowcast_runner.observation_data import download_data, load_registry, source_path
from snowcast_runner.site import deploy_ui
from snowcast_runner.site_config import load_site, configure
from test_canswe import regional_source, regional_site
from test_project_runner import project_file
from test_site_config import site_file


@pytest.fixture
def registry(regional_source, tmp_path):
    content = load_registry()
    content['datasets'][0]['source']['checksum'] = 'md5:' + hashlib.md5(regional_source.read_bytes()).hexdigest()
    target = tmp_path / 'observations.json'
    target.write_text(json.dumps(content))
    return target


def enable(site_file, registry, cache):
    raw = json.loads(site_file.read_text())
    raw['observations'] = {'registry': str(registry), 'cache': str(cache)}
    site_file.write_text(json.dumps(raw))
    return load_site(site_file)


def published_index(root):
    manifest = json.loads((root / 'observations.json').read_text())
    return json.loads((root / manifest['datasets'][0]['index']).read_text())


def test_download_streams_once_reuses_verified_cache_and_repairs_corruption(registry, regional_source, tmp_path, monkeypatch):
    calls = []
    def download(request, **kwargs):
        calls.append(request.full_url)
        return io.BytesIO(regional_source.read_bytes())
    monkeypatch.setattr(observation_data, 'urlopen', download)
    cache = tmp_path / 'cache'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: download_data('canswe', registry=registry, cache=cache), range(2)))
    assert results[0] == results[1] and len(calls) == 1
    results[0].write_bytes(b'corrupt')
    download_data('canswe', registry=registry, cache=cache)
    assert results[0].read_bytes() == regional_source.read_bytes() and len(calls) == 2
    assert not list(cache.rglob('.download-*'))


def test_interrupted_or_wrong_download_cannot_install_cache(registry, regional_source, tmp_path, monkeypatch):
    entry = load_registry(registry)['datasets'][0]
    cache = tmp_path / 'cache'
    target = source_path(entry, cache)
    monkeypatch.setattr(observation_data, 'urlopen', lambda *a, **kw: io.BytesIO(b'wrong release'))
    with pytest.raises(ValueError, match='checksum'):
        download_data('canswe', registry=registry, cache=cache)
    assert not target.exists() and not list(cache.rglob('.download-*'))
    class Interrupted(io.BytesIO):
        def read(self, *args):
            raise OSError('interrupted')
    monkeypatch.setattr(observation_data, 'urlopen', lambda *a, **kw: Interrupted())
    with pytest.raises(OSError, match='interrupted'):
        download_data('canswe', registry=registry, cache=cache)
    assert not target.exists() and not list(cache.rglob('.download-*'))
    assert main(['download-data', 'canswe', '--registry', str(registry), '--cache', str(cache),
                 '--source', str(regional_source)]) == 0
    monkeypatch.setattr(observation_data, 'urlopen', lambda *a, **kw: pytest.fail('Cached use must be offline'))
    assert main(['download-data', 'canswe', '--registry', str(registry), '--cache', str(cache)]) == 0


def test_union_cache_reuse_new_domains_empty_domains_and_disabled_dataset(registry, regional_source, regional_site, tmp_path, monkeypatch):
    site = enable(regional_site, registry, tmp_path / 'cache')
    # This fixture intentionally has only geographic catalogues (no raster assets).
    atomic_json(site.staging / '.site-config.json', site.spec)
    download_data('canswe', registry=registry, cache=site.observation_cache, source=regional_source)
    monkeypatch.setattr(observation_data, 'urlopen', lambda *a, **kw: pytest.fail('publish must never download'))
    observations.prepare_project(site, site.projects[0])
    assert {s['id'] for s in published_index(site.staging)['stations']} == {'west'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda p: observations.prepare_project(site, p), site.projects[1:]))
    index = published_index(site.staging)
    assert {s['id'] for s in index['stations']} == {'west', 'tvc', 'edge', 'near-tvc'}
    assert len(index['stations']) == 4
    before = (site.staging / 'observations.json').read_bytes()
    from snowcast_runner import canswe
    real_prepare = canswe.prepare
    monkeypatch.setattr(canswe, 'prepare', lambda *a, **kw: pytest.fail('Unchanged domains must reuse conversion'))
    for project in site.projects:
        catalogue = site.staging / 'data' / project.id / 'catalog.json'
        raw = json.loads(catalogue.read_text()); raw['latest_time'] = '2026-11-14T23:00:00Z'
        catalogue.write_text(json.dumps(raw))
        observations.prepare_project(site, project)
    assert (site.staging / 'observations.json').read_bytes() == before
    monkeypatch.setattr(canswe, 'prepare', real_prepare)
    # Zero stations is a valid contribution; it must not erase the other projects.
    catalogue = site.staging / 'data/tvc/catalog.json'
    raw = json.loads(catalogue.read_text()); raw['bounds'] = [-160, 80, -150, 85]
    catalogue.write_text(json.dumps(raw))
    observations.prepare_project(site, site.projects[1])
    assert {s['id'] for s in published_index(site.staging)['stations']} == {'west'}
    # A selected, never-published project is not required for observation conversion.
    (site.staging / 'data/overlap/catalog.json').unlink()
    observations.prepare_project(site, site.projects[0])
    assert [d['id'] for d in published_index(site.staging)['domains']] == ['west', 'tvc']
    public = json.loads((site.staging / 'observations.json').read_text())
    assert str(tmp_path) not in json.dumps(public)
    assert 'source' not in public['datasets'][0] and 'adapter' not in public['datasets'][0]


def test_missing_cache_is_partial_failure_and_ui_deploy_preserves_data(registry, site_file, tmp_path, monkeypatch, capsys):
    site = enable(site_file, registry, tmp_path / 'cache')
    configure(site)
    monkeypatch.setattr(observation_data, 'urlopen', lambda *a, **kw: pytest.fail('implicit download'))
    assert main(['publish', str(site_file), '--project', 'west', '--no-upload']) == 1
    error = capsys.readouterr().err
    assert 'Model published' in error and 'snowcast download-data canswe' in error
    assert (site.staging / 'data/west/catalog.json').exists()
    assert json.loads((site.staging / 'observations.json').read_text())['datasets'] == []
    before = (site.staging / 'observations.json').read_bytes()
    target = site.staging / 'observations/example/stations/a.json.gz'
    target.parent.mkdir(parents=True); target.write_bytes(b'existing')
    dist = tmp_path / 'dist'; dist.mkdir(); (dist / 'index.html').write_text('UI')
    (dist / 'observations.json').write_text('stale registry')
    (dist / 'observations/example/stations').mkdir(parents=True)
    (dist / 'observations/example/stations/a.json.gz').write_bytes(b'stale')
    deploy_ui(dist, site.staging)
    assert (site.staging / 'observations.json').read_bytes() == before
    assert target.read_bytes() == b'existing'


def test_remote_helper_merges_independent_publishers_and_recovers_interrupted_upload(registry, regional_source, regional_site, tmp_path, monkeypatch):
    site = enable(regional_site, registry, tmp_path / 'cache')
    atomic_json(site.staging / '.site-config.json', site.spec)
    download_data('canswe', registry=registry, cache=site.observation_cache, source=regional_source)
    payloads = [observations.prepare_project(site, p)[0] for p in site.projects]
    remote = tmp_path / 'remote'
    shutil.copytree(site.staging / 'data', remote / 'data')
    atomic_json(remote / '.site-config.json', site.spec)
    actual_run = subprocess.run
    fail_transfer = False
    def fake_transport(command, **kwargs):
        if command[0] == 'ssh':
            args = shlex.split(command[2]); args[4] = str(remote)
            return actual_run(args, **kwargs)
        if command[0] == 'rsync':
            if fail_transfer:
                raise OSError('interrupted transfer')
            listing = Path(next(a.split('=', 1)[1] for a in command if a.startswith('--files-from=')))
            for name in listing.read_text().splitlines():
                destination = remote / name; destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(site.staging / name, destination)
            return subprocess.CompletedProcess(command, 0)
        return actual_run(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', fake_transport)
    observations.upload_observations(site, payloads[0])
    before = (remote / 'observations.json').read_bytes()
    fail_transfer = True
    with pytest.raises(OSError, match='interrupted'):
        observations.upload_observations(site, payloads[1])
    assert (remote / 'observations.json').read_bytes() == before
    fail_transfer = False
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda payload: observations.upload_observations(site, payload), payloads[1:]))
    assert {s['id'] for s in published_index(remote)['stations']} == {'west', 'tvc', 'edge', 'near-tvc'}
    before = (remote / 'observations.json').read_bytes()
    bad = deepcopy(payloads[0]); bad['datasets'][0]['index']['stations'][0]['href'] = '../../escape.gz'
    with pytest.raises(ValueError, match='path'):
        commit_observations(remote, bad)
    assert (remote / 'observations.json').read_bytes() == before
    bad = deepcopy(payloads[0]); bad['spec']['title'] = 'old config'
    with pytest.raises(ValueError, match='configuration changed'):
        commit_observations(remote, bad)


def test_registry_disables_dataset_and_rejects_invalid_entries(registry, site_file, tmp_path):
    site = enable(site_file, registry, tmp_path / 'cache')
    configure(site)
    raw = load_registry(registry)
    raw['datasets'][0]['enabled'] = False
    registry.write_text(json.dumps(raw))
    configure(load_site(site_file))
    assert json.loads((site.staging / 'observations.json').read_text())['datasets'] == []
    for field, value in [('id', '../escape'), ('selection', {'nearby_km': -1}), ('adapter', 'unknown')]:
        bad = deepcopy(raw); bad['datasets'][0][field] = value
        registry.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            load_registry(registry)


def test_dataset_failures_retain_previous_contributions_and_allow_other_datasets(registry, regional_source, regional_site, tmp_path, monkeypatch):
    raw = load_registry(registry)
    raw['datasets'].append({**deepcopy(raw['datasets'][0]), 'id': 'other-network', 'label': 'Other network'})
    registry.write_text(json.dumps(raw))
    site = enable(regional_site, registry, tmp_path / 'cache')
    atomic_json(site.staging / '.site-config.json', site.spec)
    download_data('canswe', registry=registry, cache=site.observation_cache, source=regional_source)
    _, errors = observations.prepare_project(site, site.projects[0])
    assert len(errors) == 1 and 'download-data other-network' in errors[0]
    assert [d['id'] for d in json.loads((site.staging / 'observations.json').read_text())['datasets']] == ['canswe']
    download_data('other-network', registry=registry, cache=site.observation_cache, source=regional_source)
    _, errors = observations.prepare_project(site, site.projects[0])
    assert not errors
    before = (site.staging / 'observations.json').read_bytes()
    assert len(json.loads(before)['datasets']) == 2
    from snowcast_runner import canswe
    (site.staging / '.observation-build/canswe-west.json').unlink()
    actual_prepare = canswe.prepare
    def fail_canswe(*args, **kwargs):
        if kwargs['entry']['id'] == 'canswe':
            raise OSError('conversion interrupted')
        return actual_prepare(*args, **kwargs)
    monkeypatch.setattr(canswe, 'prepare', fail_canswe)
    _, errors = observations.prepare_project(site, site.projects[0])
    assert errors == ['conversion interrupted']
    assert (site.staging / 'observations.json').read_bytes() == before
