"""Independent data publication and static UI installation on a local/mounted site."""
import json
import os
from pathlib import Path
import shutil
import tempfile

from .cog_store import atomic_json, store_lock, site_action
from .publish_cogs import publish


def register(site, project, catalogue_path):
    identity = project.id
    if (site / '.site-config.json').exists():
        site_action('register-site', site, project_id=identity)
        return
    # Every publisher merges the latest registry under the same host-side lock.
    with store_lock(site):
        index = site / 'domains.json'
        registry = json.loads(index.read_text()) if index.exists() else {'version': 1, 'domains': []}
        if registry.get('version') != 1 or not isinstance(registry.get('domains'), list):
            raise ValueError('Invalid site domain registry; existing file retained')
        entries = {entry['id']: entry for entry in registry['domains']}
        if len(entries) != len(registry['domains']):
            raise ValueError('Duplicate site domain IDs')
        # Read current metadata, not the caller's potentially superseded result.
        catalogue = json.loads((site / catalogue_path).read_text())
        if catalogue.get('domain', {}).get('id') != identity:
            raise ValueError('Catalogue domain identity does not match registration')
        entries[identity] = {'id': identity, 'name': catalogue['domain']['name'], 'catalogue': catalogue_path}
        registry['domains'] = [entries[key] for key in sorted(entries)]
        atomic_json(index, registry)


def publish_project(project, site):
    site = Path(site).resolve()
    if site == project.work or site.is_relative_to(project.work):
        raise ValueError('The site must be outside the project work directory')
    if (site / '.site-config.json').exists():
        site_action('check-site', site, project_id=project.id)
    # Separate physical roots also bound cleanup and allow identical timestamps.
    relative = Path('data') / project.id
    destination = site / relative
    for part in (site / 'data', destination):
        if part.is_symlink():
            raise ValueError('Domain publication directories cannot be symlinks')
    dx, dy = project.postprocess['grid']['resolution']
    metadata = {'id': project.id, 'project': project.id, 'name': project.name}
    folder = project.work / 'postprocess'
    catalogue = publish([folder / 'archive_tiff', folder / 'tiff'], destination,
                        grid=f'{dx:g}x{dy:g}', domain=metadata, ranges=project.display.get('ranges'))
    for directory in (site, site / 'data', site / 'data' / project.id):
        directory.chmod(0o755)
    # The domain becomes discoverable only after its complete catalogue exists.
    register(site, project, (relative / 'catalog.json').as_posix())
    return catalogue


def deploy_ui(dist, site):
    dist, site = Path(dist).resolve(), Path(site).resolve()
    if not (dist / 'index.html').is_file():
        raise ValueError('UI dist directory must contain a built index.html')
    if dist == site or dist.is_relative_to(site) or site.is_relative_to(dist):
        raise ValueError('UI build and site directories must be separate')
    files = []
    reserved = {'data', 'domains.json', 'site.json', '.site-config.json', 'catalog.json', '.publish.lock', 'demo', 'demo-site'}
    for source in dist.rglob('*'):
        relative = source.relative_to(dist)
        if source.is_symlink():
            raise ValueError(f'UI build contains a symlink: {relative}')
        if source.is_file() and relative.parts[0] not in reserved:
            files.append((source, relative))
    with store_lock(site):
        # Content-addressed assets first, HTML entrypoints last. Keep old assets
        # for already-open pages and leave all published simulation data intact.
        for source, relative in sorted(files, key=lambda item: item[1].suffix == '.html'):
            target = site / relative
            if relative.as_posix() == 'download-index.json' and target.exists():
                continue
            if any(p.is_symlink() for p in (target, *target.parents) if p != site.parent):
                raise ValueError(f'UI destination contains a symlink: {relative}')
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.ui-', dir=target.parent)
            try:
                with os.fdopen(fd, 'wb') as output, source.open('rb') as input_file:
                    shutil.copyfileobj(input_file, output)
                    output.flush()
                    os.fchmod(output.fileno(), 0o644)
                    os.fsync(output.fileno())
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
            for directory in (target.parent, *target.parent.parents):
                if directory == site.parent:
                    break
                directory.chmod(0o755)
