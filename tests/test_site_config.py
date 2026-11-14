from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest

from snowcast_runner.cli import main
from snowcast_runner.cog_store import site_action
from snowcast_runner.project import load_project
from snowcast_runner.site import publish_project, deploy_ui
from snowcast_runner.site_config import configure, load_site, publish_selected
from project_helpers import clone_project
from test_project_runner import project_file, exports


@pytest.fixture
def site_file(project_file, tmp_path):
    files = [project_file, clone_project(project_file, 'tvc'), clone_project(project_file, 'third')]
    for file in files:
        exports(load_project(file).work / 'postprocess/tiff')
    target = tmp_path / 'sites/snowcast.json'
    target.parent.mkdir()
    target.write_text(json.dumps({'version': 1, 'observations': False, 'title': 'SnowCast',
        'projects': [str(p) for p in files], 'staging': '../site staging',
        'deploy': {'host': 'fixture.example', 'directory': str(tmp_path / 'remote site')}}))
    return target


def test_site_cli_and_public_config_hide_execution_paths(site_file, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path.parent)
    assert main(['site', 'validate', str(site_file)]) == 0
    site = load_site(site_file)
    assert not site.staging.exists()
    assert main(['site', 'configure', str(site_file)]) == 0
    public = json.loads((site.staging / 'site.json').read_text())
    assert [d['id'] for d in public['domains']] == ['west', 'tvc', 'third']
    assert not any(d['available'] for d in public['domains'])
    assert str(tmp_path) not in json.dumps(public)
    assert 'fixture.example' not in json.dumps(public)
    assert main(['publish', str(site_file), '--project', 'tvc', '--no-upload']) == 0
    public = json.loads((site.staging / 'site.json').read_text())
    assert [d['id'] for d in public['domains'] if d['available']] == ['tvc']


@pytest.mark.parametrize('with_deploy', [True, False])
def test_no_upload_publishes_locally_without_remote_commands(site_file, monkeypatch, capsys, with_deploy):
    raw = json.loads(site_file.read_text())
    remote = Path(raw['deploy']['directory'])
    if not with_deploy:
        raw.pop('deploy')
        site_file.write_text(json.dumps(raw))
    site = load_site(site_file); configure(site)

    def unexpected_process(*args, **kwargs):
        pytest.fail('Local publication must not invoke SSH, rsync or a model job')

    monkeypatch.setattr(subprocess, 'run', unexpected_process)
    assert main(['publish', str(site_file), '--project', 'tvc', '--no-upload']) == 0
    assert 'local only; no upload' in capsys.readouterr().out
    public = json.loads((site.staging / 'site.json').read_text())
    assert [d['id'] for d in public['domains'] if d['available']] == ['tvc']
    assert (site.staging / 'data/tvc/catalog.json').exists()
    assert not remote.exists()


def test_upload_default_requires_destination_before_conversion(site_file, capsys):
    raw = json.loads(site_file.read_text()); raw.pop('deploy')
    site_file.write_text(json.dumps(raw))
    site = load_site(site_file); configure(site)
    before = (site.staging / 'site.json').read_bytes()
    assert main(['publish', str(site_file), '--project', 'tvc']) == 1
    assert '--no-upload' in capsys.readouterr().err
    assert (site.staging / 'site.json').read_bytes() == before
    assert not (site.staging / 'data').exists()


@pytest.mark.parametrize('arguments', [
    ['site', 'publish', 'site.json', '--project', 'tvc'],
    ['publish', 'project/', '--site-dir', 'website/'],
    ['publish', 'site.json', '--project', 'tvc', '--upload'],
])
def test_replaced_publish_forms_fail_before_side_effects(arguments, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as result:
        main(arguments)
    assert result.value.code == 2
    assert not list(tmp_path.iterdir())


def test_independent_concurrent_publishers_preserve_other_projects(site_file):
    site = load_site(site_file); configure(site)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda p: publish_selected(site, p.id, remote=False), site.projects))
    before = (site.staging / 'data/tvc/catalog.json').read_bytes()
    publish_selected(site, 'west', remote=False)
    public = json.loads((site.staging / 'site.json').read_text())
    assert all(d['available'] for d in public['domains'])
    assert [d['id'] for d in public['domains']] == ['west', 'tvc', 'third']
    assert (site.staging / 'data/tvc/catalog.json').read_bytes() == before


def test_failed_conversion_retains_live_site_and_other_catalogues(site_file):
    site = load_site(site_file); configure(site)
    publish_selected(site, 'west', remote=False)
    before = (site.staging / 'site.json').read_bytes()
    shutil.rmtree(site.projects[1].work / 'postprocess/tiff')
    with pytest.raises(ValueError):
        publish_selected(site, 'tvc', remote=False)
    assert (site.staging / 'site.json').read_bytes() == before


def test_explicit_selection_removal_rejects_old_publishers_without_deleting_data(site_file):
    old = load_site(site_file); configure(old); publish_selected(old, 'tvc', remote=False)
    catalogue = old.staging / 'data/tvc/catalog.json'
    before = catalogue.read_bytes()
    raw = json.loads(site_file.read_text()); raw['projects'] = raw['projects'][:1]
    site_file.write_text(json.dumps(raw))
    new = load_site(site_file); configure(new)
    with pytest.raises(ValueError, match='configuration changed'):
        publish_selected(old, 'tvc', remote=False)
    with pytest.raises(ValueError, match='not selected'):
        publish_project(old.projects[1], old.staging)
    assert catalogue.read_bytes() == before
    assert [d['id'] for d in json.loads((old.staging / 'site.json').read_text())['domains']] == ['west']


def test_duplicate_ids_and_staging_in_project_work_are_rejected(site_file):
    raw = json.loads(site_file.read_text())
    raw['projects'] += raw['projects'][:1]
    site_file.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match='duplicate'):
        load_site(site_file)
    raw['projects'].pop()
    raw['staging'] = str(Path(raw['projects'][0]).parent / 'work/site')
    site_file.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match='outside every project'):
        load_site(site_file)


def test_ui_install_preserves_authoritative_registry(site_file, tmp_path):
    site = load_site(site_file); configure(site)
    before = (site.staging / 'site.json').read_bytes()
    dist = tmp_path / 'dist'; dist.mkdir()
    (dist / 'index.html').write_text('UI')
    (dist / 'site.json').write_text('wrong')
    (dist / '.site-config.json').write_text('wrong')
    deploy_ui(dist, site.staging)
    assert (site.staging / 'site.json').read_bytes() == before
    assert json.loads((site.staging / '.site-config.json').read_text()) == site.spec


def test_standalone_remote_helper_and_upload_register_only_complete_catalogues(site_file, monkeypatch):
    site = load_site(site_file)
    remote = Path(site.deploy['directory'])
    actual_run = subprocess.run
    fail_transfer = False

    def fake_transport(command, **kwargs):
        if command[0] == 'ssh':
            return actual_run(shlex.split(command[2]), **kwargs)
        if command[0] == 'rsync':
            if fail_transfer:
                raise OSError('transfer interrupted')
            listing = Path(next(arg.split('=', 1)[1] for arg in command if arg.startswith('--files-from=')))
            source = Path(command[-2])
            destination = Path(command[-1].split(':', 1)[1])
            for name in listing.read_text().splitlines():
                target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, target)
            return subprocess.CompletedProcess(command, 0)
        return actual_run(command, **kwargs)

    monkeypatch.setattr(subprocess, 'run', fake_transport)
    assert main(['site', 'configure', str(site_file), '--upload']) == 0
    assert main(['publish', str(site_file), '--project', 'west']) == 0
    before = (remote / 'site.json').read_bytes()
    fail_transfer = True
    assert main(['publish', str(site_file), '--project', 'tvc']) == 1
    assert (remote / 'site.json').read_bytes() == before
    assert not (remote / 'data/tvc/catalog.json').exists()
    fail_transfer = False
    assert main(['publish', str(site_file), '--project', 'tvc']) == 0
    public = json.loads((remote / 'site.json').read_text())
    assert [d['id'] for d in public['domains'] if d['available']] == ['west', 'tvc']
    assert not (remote / 'download-index.json').exists()  # No Western-only archive refresh.


def test_host_rejects_stale_registration_and_symlink_catalogues(site_file):
    site = load_site(site_file); configure(site)
    changed = {**site.spec, 'title': 'changed elsewhere'}
    site_action('configure-site', site.staging, changed)
    with pytest.raises(ValueError, match='configuration changed'):
        site_action('register-site', site.staging, site.spec, 'tvc')
    root = site.staging / 'data/tvc'; root.mkdir(parents=True)
    (root / 'catalog.json').symlink_to(site_file)
    before = (site.staging / 'site.json').read_bytes()
    with pytest.raises(ValueError, match='symlinks'):
        site_action('register-site', site.staging, changed, 'tvc')
    assert (site.staging / 'site.json').read_bytes() == before
