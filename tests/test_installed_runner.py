"""Build/install only the package, then exercise it with no legacy imports."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from test_project_runner import project_file, configure_fake_pipeline


def checked(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, **kwargs)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_wheel_runs_project_through_postprocess_outside_checkout(project_file, tmp_path):
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
for name in ['cli', 'chm_config', 'forcing', 'met', 'model', 'backfill', 'rasters', 'jobs', 'state', 'site', 'publish_cogs', 'upload', 'downloads']:
    importlib.import_module('snowcast_runner.' + name)
from snowcast_runner.cli import main
raise SystemExit(main(sys.argv[1:]))
'''
    configure_fake_pipeline(project_file, tmp_path)
    outside = tmp_path / 'unrelated-cwd'
    outside.mkdir()
    for action in ('validate', 'prepare', 'run', 'postprocess', 'status'):
        checked([sys.executable, '-I', '-c', bootstrap, str(installed), action, str(project_file)], cwd=outside)
    state = json.loads((project_file.parent / 'work/status.json').read_text())
    assert state['project'] == 'west' and state['state'] == 'completed'
    assert state['output']['times'] == ['20261108T230000', '20261109T230000']
    assert len(list((project_file.parent / 'work/postprocess/tiff').glob('*.tiff'))) == 4
    assert not list(outside.iterdir())
    assert (installed / 'bin/snowcast').is_file()
    checked([str(installed / 'bin/snowcast'), '--help'], cwd=outside,
            env={**os.environ, 'PYTHONPATH': str(installed)})


@pytest.mark.parametrize('module', ['publish_cogs', 'cog_store', 'upload', 'downloads'])
def test_package_utilities_run_from_an_unrelated_directory(module, tmp_path):
    checked([sys.executable, '-m', 'snowcast_runner.' + module, '--help'], cwd=tmp_path)
