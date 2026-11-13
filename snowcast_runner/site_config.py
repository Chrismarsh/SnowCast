"""Authored site selection and independent publication of model projects."""
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import subprocess

from .cog_store import site_action, validate_site_spec
from .project import Project, keys, load_project, path
from .site import publish_project
from .state import workspace
from .upload import _remote_store, _validate_destination, upload


@dataclass(frozen=True)
class Site:
    file: Path
    staging: Path
    projects: list[Project]
    spec: dict
    deploy: dict | None


def load_site(filename):
    filename = Path(filename).expanduser().resolve()
    raw = json.loads(filename.read_text())
    keys(raw, 'version title projects staging deploy overview_ranges', 'site')
    if type(raw.get('version')) is not int or raw['version'] != 1:
        raise ValueError('site.version must be 1')
    entries = raw.get('projects')
    if not isinstance(entries, list) or not entries:
        raise ValueError('site.projects must list project folders or manifest paths')
    projects = [load_project(path(filename.parent, value)) for value in entries]
    staging = path(filename.parent, raw.get('staging'))
    if any(staging == p.work or staging.is_relative_to(p.work) for p in projects):
        raise ValueError('Site staging must be outside every project work directory')
    spec = {'version': 1, 'title': raw.get('title', 'SnowCast'),
            'domains': [{'id': p.id, 'name': p.name, 'catalogue': f'data/{p.id}/catalog.json'} for p in projects],
            'overview_ranges': raw.get('overview_ranges', {})}
    validate_site_spec(spec)
    deploy = raw.get('deploy')
    if deploy is not None:
        keys(deploy, 'host directory', 'site.deploy')
        if not all(isinstance(deploy.get(k), str) for k in ('host', 'directory')):
            raise ValueError('site.deploy requires host and directory')
        _validate_destination(deploy['host'], deploy['directory'])
    return Site(filename, staging, projects, spec, deploy)


def remote_site(site, action, project_id=None):
    if site.deploy is None:
        raise ValueError('--upload requires site.deploy.host and site.deploy.directory')
    command = _remote_store(site.deploy['host'], site.deploy['directory'], action, project_id or '')
    # Configuration conflicts need operator action, not hours of transfer retries.
    subprocess.run(command, input=json.dumps(site.spec).encode(), check=True)


def configure(site, *, remote=False):
    if remote and site.deploy is None:
        raise ValueError('--upload requires site.deploy.host and site.deploy.directory')
    site_action('configure-site', site.staging, site.spec)
    if remote:
        remote_site(site, 'configure-site')


def publish_selected(site, project_id, *, remote=True):
    project = next((p for p in site.projects if p.id == project_id), None)
    if project is None:
        raise ValueError(f'Project {project_id} is not selected for this site')
    if remote and site.deploy is None:
        raise ValueError('Publishing uploads by default; set site.deploy.host and site.deploy.directory, '
                         'or use --no-upload for local-only publication')
    site_action('check-site', site.staging, site.spec, project_id)
    if remote:
        remote_site(site, 'check-site', project_id)
    with workspace(project):
        catalogue = publish_project(project, site.staging)
        if remote:
            destination = str(PurePosixPath(site.deploy['directory']) / 'data' / project_id)
            upload(site.staging / 'data' / project_id, site.deploy['host'], destination,
                   refresh_downloads=False)
            remote_site(site, 'register-site', project_id)
    return catalogue
