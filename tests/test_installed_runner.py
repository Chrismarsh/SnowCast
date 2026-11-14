"""Build/install only the package, then exercise it with no legacy imports."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from test_project_runner import project_file, configure_fake_pipeline
from test_canswe import regional_source, regional_site


def checked(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, **kwargs)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_wheel_runs_project_through_postprocess_outside_checkout(project_file, tmp_path, regional_source, regional_site):
    root = Path(__file__).resolve().parents[1]
    source, wheels, installed = (tmp_path / name for name in ('package-source', 'wheels', 'installed'))
    source.mkdir()
    shutil.copy(root / 'pyproject.toml', source)
    shutil.copytree(root / 'snowcast_runner', source / 'snowcast_runner', ignore=shutil.ignore_patterns('__pycache__'))
    checked([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation', '--no-index',
             '--wheel-dir', str(wheels), str(source)], cwd=tmp_path)
    wheel = next(wheels.glob('*.whl'))
    with zipfile.ZipFile(wheel) as archive:
        assert not any(name.startswith(('met/', 'postprocess/', 'webupload/')) for name in archive.namelist())
    checked([sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-index', '--target', str(installed), str(wheel)], cwd=tmp_path)
    # -I ignores the cwd and PYTHONPATH. A blocker also excludes editable-install
    # fallbacks in the test environment, so a legacy dependency cannot pass here.
    bootstrap = '''import importlib, importlib.abc, pathlib, sys
installed = pathlib.Path(sys.argv.pop(1))
sys.path.insert(0, str(installed))
class NoLegacy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'met', 'postprocess', 'webupload'}:
            raise ImportError('Legacy checkout import: ' + fullname)
sys.meta_path.insert(0, NoLegacy())
import snowcast_runner
assert pathlib.Path(snowcast_runner.__file__).is_relative_to(installed)
for name in ['cli', 'chm_config', 'forcing', 'met', 'model', 'backfill', 'rasters', 'jobs', 'state', 'site', 'site_config', 'publish_cogs', 'upload', 'downloads', 'canswe', 'observation_data', 'observations', 'archive', 'archive_store']:
    importlib.import_module('snowcast_runner.' + name)
from snowcast_runner.cli import main
raise SystemExit(main(sys.argv[1:]))
'''
    configure_fake_pipeline(project_file, tmp_path)
    outside = tmp_path / 'unrelated-cwd'
    outside.mkdir()
    for action in ('validate', 'prepare', 'run', 'postprocess', 'status'):
        checked([sys.executable, '-I', '-c', bootstrap, str(installed), action, str(project_file)], cwd=outside)
    raw_project = json.loads(project_file.read_text())
    raw_project['archive'] = {'destinations': [{'id': 'backup', 'backend': 'local',
        'directory': str(tmp_path / 'originals'), 'public_url': 'https://archive.example/west/'}]}
    project_file.write_text(json.dumps(raw_project))
    checked([sys.executable, '-I', '-c', bootstrap, str(installed), 'archive', str(project_file)], cwd=outside)
    assert (tmp_path / 'originals/archive-index.json').is_file()
    state = json.loads((project_file.parent / 'work/status.json').read_text())
    assert state['project'] == 'west' and state['state'] == 'completed'
    assert state['output']['times'] == ['20261108T230000', '20261109T230000']
    assert len(list((project_file.parent / 'work/postprocess/tiff').glob('*.tiff'))) == 4
    site_file = tmp_path / 'site.json'
    site_file.write_text(json.dumps({'version': 1, 'observations': False, 'projects': [str(project_file)], 'staging': 'website'}))
    for action in ('validate', 'configure'):
        checked([sys.executable, '-I', '-c', bootstrap, str(installed), 'site', action, str(site_file)], cwd=outside)
    checked([sys.executable, '-I', '-c', bootstrap, str(installed), 'publish', str(site_file),
             '--project', 'west', '--no-upload'], cwd=outside)
    assert json.loads((tmp_path / 'website/site.json').read_text())['domains'][0]['available'] is True
    # The installed wheel carries the registry; source data is never packaged.
    registry = json.loads((installed / 'snowcast_runner/observations.json').read_text())
    registry['datasets'][0]['source']['checksum'] = 'md5:' + hashlib.md5(regional_source.read_bytes()).hexdigest()
    registry_file = tmp_path / 'observations.json'
    registry_file.write_text(json.dumps(registry))
    checked([sys.executable, '-I', '-c', bootstrap, str(installed), 'download-data', 'canswe',
             '--registry', str(registry_file), '--source', str(regional_source), '--cache', str(tmp_path / 'cache')], cwd=outside)
    raw = json.loads(site_file.read_text())
    raw['observations'] = {'registry': str(registry_file), 'cache': str(tmp_path / 'cache')}
    site_file.write_text(json.dumps(raw))
    checked([sys.executable, '-I', '-c', bootstrap, str(installed), 'site', 'configure', str(site_file)], cwd=outside)
    checked([sys.executable, '-I', '-c', bootstrap, str(installed), 'publish', str(site_file), '--project', 'west', '--no-upload'], cwd=outside)
    assert json.loads((tmp_path / 'website/observations.json').read_text())['datasets'][0]['id'] == 'canswe'
    assert not list(outside.iterdir())
    assert (installed / 'bin/snowcast').is_file()
    checked([str(installed / 'bin/snowcast'), '--help'], cwd=outside,
            env={**os.environ, 'PYTHONPATH': str(installed)})


@pytest.mark.parametrize('module', ['publish_cogs', 'cog_store', 'upload', 'downloads'])
def test_package_utilities_run_from_an_unrelated_directory(module, tmp_path):
    checked([sys.executable, '-m', 'snowcast_runner.' + module, '--help'], cwd=tmp_path)
