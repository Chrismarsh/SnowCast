"""Archive original project rasters independently of Web UI publication.

Receipts record completed destinations. Publishing consumes those receipts without
connecting to archive storage. Backends never prune remote history.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import tempfile
from urllib.parse import urlsplit

from .archive_store import atomic_file, claim, commit, safe_path
from .cog_store import atomic_json
from .project import keys, path, slug
from .state import workspace
from .upload import _validate_destination


def http_url(value, name):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        raise ValueError(f'{name} must be an HTTP(S) URL')
    parts = urlsplit(value)
    if parts.scheme not in ('http', 'https') or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError(f'{name} must be an HTTP(S) URL without credentials, query or fragment')
    return value.rstrip('/') + '/'


def destinations(raw, base, project_id, work):
    # An external JSON file can be shared using {project} in path/prefix/URL.
    if isinstance(raw, str):
        file = path(base, raw)
        raw, base = json.loads(file.read_text()), file.parent
    keys(raw, 'destinations', 'archive')
    entries = raw.get('destinations', [])
    if not isinstance(entries, list):
        raise ValueError('archive.destinations must be a list')
    result, ids, roots = [], set(), set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Archive destinations must be objects')
        backend = entry.get('backend')
        fields = {'local': 'directory', 'rsync': 'host directory',
                  's3': 'bucket prefix endpoint_url profile region'}
        if backend not in fields:
            raise ValueError('archive backend must be local, rsync or s3')
        keys(entry, 'id name backend public_url ' + fields[backend], 'archive destination')
        entry = dict(entry)
        identifier = slug(entry.get('id'), 'archive destination id')
        if identifier in ids:
            raise ValueError(f'Duplicate archive destination ID: {identifier}')
        ids.add(identifier)
        entry.setdefault('name', identifier)
        if not isinstance(entry['name'], str) or not entry['name'].strip():
            raise ValueError('Archive destination name must be nonempty')
        for field in ('directory', 'prefix', 'public_url'):
            if field in entry:
                if not isinstance(entry[field], str) or not entry[field] or any(ord(c) < 32 for c in entry[field]):
                    raise ValueError(f'archive.{field} must be a nonempty string')
                entry[field] = entry[field].replace('{project}', project_id)
                if '{' in entry[field] or '}' in entry[field]:
                    raise ValueError('Only {project} is supported in archive paths and URLs')
        if 'public_url' in entry:
            entry['public_url'] = http_url(entry['public_url'], 'archive.public_url')
        if backend == 'local':
            directory = path(base, entry.get('directory'))
            if directory == work or directory.is_relative_to(work) or work.is_relative_to(directory):
                raise ValueError('Local archive must be outside and not contain project work/')
            entry['directory'] = str(directory)
        elif backend == 'rsync':
            if not all(isinstance(entry.get(k), str) for k in ('host', 'directory')):
                raise ValueError('rsync archive requires host and directory')
            _validate_destination(entry['host'], entry['directory'])
            if '..' in PurePosixPath(entry['directory']).parts or entry['directory'] == '/':
                raise ValueError('Use a dedicated absolute archive directory without ..')
        else:
            if not isinstance(entry.get('bucket'), str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', entry['bucket']):
                raise ValueError('s3 archive requires a bucket name')
            prefix = entry.get('prefix', '')
            if not re.fullmatch(r'[A-Za-z0-9_./-]+', prefix) or prefix.startswith('/') or any(p in ('.', '..', '') for p in prefix.rstrip('/').split('/')):
                raise ValueError('s3 archive requires a dedicated relative prefix')
            entry['prefix'] = prefix.rstrip('/')
            for field in ('profile', 'region'):
                if field in entry and (not isinstance(entry[field], str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', entry[field])):
                    raise ValueError(f'Invalid archive S3 {field}')
            if 'endpoint_url' in entry:
                entry['endpoint_url'] = http_url(entry['endpoint_url'], 'archive.endpoint_url').rstrip('/')
        identity = tuple(entry.get(k) for k in ('backend', 'host', 'directory', 'endpoint_url', 'bucket', 'prefix'))
        if identity in roots:
            raise ValueError('Archive destinations must have separate storage roots')
        roots.add(identity)
        result.append(entry)
    return result


def config_hash(destination, *, storage=False):
    if storage:
        destination = {k: destination[k] for k in ('backend', 'host', 'directory', 'bucket', 'prefix', 'endpoint_url') if k in destination}
    return hashlib.sha256(json.dumps(destination, sort_keys=True).encode()).hexdigest()


def ascii_resolution(file):
    # ASCII filenames omit spacing. Read the actual header rather than label
    # historical outputs with today's possibly changed export configuration.
    with file.open() as stream:
        for _ in range(8):
            fields = stream.readline(4096).split()
            if len(fields) == 2 and fields[0].lower() == 'cellsize':
                spacing = float(fields[1])
                if math.isfinite(spacing) and spacing > 0:
                    return [spacing, spacing]
                break
    raise ValueError(f'ASCII product has no valid cellsize header: {file}')


def inventory(project):
    """Select current revisions over archived copies, including dataset sidecars."""
    folder = project.work / 'postprocess'
    saved_grid = folder / 'grid.json'
    if saved_grid.exists() and json.loads(saved_grid.read_text())['settings'] != project.postprocess['grid']:
        raise ValueError('Grid settings differ from existing products; restore the project grid before archiving')
    sources, entries = {}, {}
    patterns = [('tiff', 'tiff', re.compile(r'(swe|snowdepthavg|t)-([^_]+)_(\d{8}T\d{6})\.tiff?$'), '%Y%m%dT%H%M%S'),
                ('ascii', 'asc', re.compile(r'(swe|snowdepthavg|t)_(\d{14})\.asc$'), '%Y%m%d%H%M%S')]
    for local, remote, pattern, time_format in patterns:
        datasets = {}
        for directory in (folder / f'archive_{local}', folder / local):
            if not directory.exists():
                continue
            for file in directory.iterdir():
                match = pattern.fullmatch(file.name)
                if match:
                    datasets[file.name] = (file, match)
        for name, (file, match) in sorted(datasets.items()):
            if file.is_symlink() or not file.is_file():
                raise ValueError(f'Archive product cannot be a symlink or directory: {file}')
            stamp = match.groups()[-1]
            time = datetime.strptime(stamp, time_format).strftime('%Y-%m-%dT%H:%M:%SZ')
            is_tiff = local == 'tiff'
            grid = project.postprocess['grid']
            resolution = grid['resolution'] if is_tiff else ascii_resolution(file)
            if is_tiff and match[2] != f'{resolution[0]:g}x{resolution[1]:g}':
                raise ValueError(f'Archive product grid does not match project: {name}')
            relative = f'{remote}/{name}'
            companions = [p for p in file.parent.glob(name + '.*') if p.is_file() or p.is_symlink()]
            if not is_tiff and file.with_suffix('.prj').exists():
                companions.append(file.with_suffix('.prj'))
            for source in [file, *companions]:
                if source.is_symlink():
                    raise ValueError(f'Archive sidecar cannot be a symlink: {source}')
                sources[f'{remote}/{source.name}'] = source
            entries[relative] = {'name': name, 'path': relative, 'variable': match[1], 'time': time,
                                 'format': 'GeoTIFF' if is_tiff else 'ASCII', 'resolution': resolution,
                                 'crs': str(grid['crs']) if is_tiff else 'EPSG:4326', 'bytes': file.stat().st_size,
                                 'sidecars': [f'{remote}/{p.name}' for p in companions]}
    if not entries:
        raise ValueError('No original TIFF/ASCII products found; run postprocess first')
    return sources, entries


def remote_helper(destination, action, project_id, content=None):
    source = Path(__file__).with_name('archive_store.py').read_text()
    command = ' '.join(shlex.quote(s) for s in ('python3', '-c', source, action, destination['directory'], project_id))
    subprocess.run(['ssh', destination['host'], command], input=content, check=True)


class Local:
    def __init__(self, destination):
        self.destination = destination
        self.root = Path(destination['directory'])

    def claim(self, project_id, temporary):
        claim(self.root, project_id)

    def transfer(self, staging):
        for source in staging.rglob('*'):
            if source.is_file():
                target = safe_path(self.root, source.relative_to(staging))
                with source.open('rb') as stream:
                    atomic_file(target, stream)

    def commit(self, project_id, index_file):
        commit(self.root, index_file.read_bytes())


class Rsync:
    def __init__(self, destination):
        self.destination = destination

    def claim(self, project_id, temporary):
        remote_helper(self.destination, 'claim', project_id)

    def transfer(self, staging):
        d = self.destination
        subprocess.run(['rsync', '-rtp', '--copy-links', '--checksum', '--chmod=D755,F644', '--protect-args',
                        f'{staging}/', f'{d["host"]}:{d["directory"]}/'], check=True)

    def commit(self, project_id, index_file):
        remote_helper(self.destination, 'commit', project_id, index_file.read_bytes())


class S3:
    def __init__(self, destination):
        self.destination = destination
        self.options = ['aws', '--no-cli-pager']
        for field in ('profile', 'region', 'endpoint_url'):
            if field in destination:
                self.options += ['--' + field.replace('_', '-'), destination[field]]
        self.root = f's3://{destination["bucket"]}/{destination["prefix"]}/'

    def claim(self, project_id, temporary):
        # Conditional creation prevents two projects claiming the same prefix.
        identity = {'version': 1, 'project': project_id}
        owner = temporary / 'owner.json'
        owner.write_text(json.dumps(identity))
        d = self.destination
        key = d['prefix'] + '/.snowcast-archive-owner.json'
        result = subprocess.run(self.options + ['s3api', 'put-object', '--bucket', d['bucket'], '--key', key,
                                '--body', str(owner), '--if-none-match', '*'], capture_output=True, text=True)
        if result.returncode:
            if not re.search(r'PreconditionFailed|\b412\b', result.stderr):
                raise RuntimeError(f'S3 ownership check failed: {result.stderr.strip()}')
            subprocess.run(self.options + ['s3', 'cp', self.root + '.snowcast-archive-owner.json', str(owner),
                                          '--only-show-errors'], check=True)
            if json.loads(owner.read_text()) != identity:
                raise ValueError('S3 archive prefix belongs to another project')

    def transfer(self, staging):
        # Only changed files are staged. cp resends same-size revisions, unlike sync.
        subprocess.run(self.options + ['s3', 'cp', str(staging) + '/', self.root, '--recursive',
                                      '--only-show-errors', '--no-progress', '--follow-symlinks'], check=True)

    def commit(self, project_id, index_file):
        subprocess.run(self.options + ['s3', 'cp', str(index_file), self.root + 'archive-index.json',
                                      '--content-type', 'application/json', '--cache-control', 'no-cache',
                                      '--only-show-errors'], check=True)


BACKENDS = {'local': Local, 'rsync': Rsync, 's3': S3}


def receipt(project, destination, *, for_archive=False):
    file = safe_path(project.work / 'archive', destination['id'] + '.json')
    previous = json.loads(file.read_text()) if file.exists() else None
    if previous and previous.get('config_hash') != config_hash(destination):
        if not for_archive or previous.get('storage_hash') != config_hash(destination, storage=True):
            previous = None
    return file, previous


def archive_project(project, *, selected=None, dry_run=False, force=False):
    if not project.archive:
        raise ValueError('No archive destinations configured; add archive.destinations to the project JSON')
    selected = set(selected or [d['id'] for d in project.archive])
    unknown = selected - {d['id'] for d in project.archive}
    if unknown:
        raise ValueError(f'Unknown archive destinations: {sorted(unknown)}')
    errors = []
    with workspace(project):
        sources, entries = inventory(project)
        fingerprints = {key: [p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns] for key, p in sources.items()}
        for destination in project.archive:
            if destination['id'] not in selected:
                continue
            try:
                file, previous = receipt(project, destination, for_archive=True)
                old_fingerprints = previous['fingerprints'] if previous else {}
                changed = [key for key in sources if force or fingerprints[key] != old_fingerprints.get(key)]
                old_entries = {f['path']: f for f in previous['index']['sources'][0]['files']} if previous else {}
                for key, entry in entries.items():
                    removed = set(old_entries.get(key, {}).get('sidecars', [])) - set(entry['sidecars'])
                    if removed:
                        raise ValueError(f'Sidecars removed for {key}; restore them or use a new archive root: {sorted(removed)}')
                combined = {**old_entries, **entries}
                index = {'version': 2, 'project': {'id': project.id, 'name': project.name},
                         'indexed_at': datetime.now(timezone.utc).isoformat(), 'sources': [{
                             'id': destination['id'], 'name': destination['name'], 'url': destination.get('public_url'),
                             'files': [combined[k] for k in sorted(combined)]}]}
                target = (f'{destination["host"]}:{destination["directory"]}' if destination['backend'] == 'rsync'
                          else f's3://{destination["bucket"]}/{destination["prefix"]}/' if destination['backend'] == 's3'
                          else destination['directory'])
                print(f'{project.id} → {destination["id"]} ({target}): '
                      f'{len(changed)} changed files, {sum(sources[k].stat().st_size for k in changed)} bytes'
                      + (' [dry run; no destination accessed]' if dry_run else ''), flush=True)
                if dry_run:
                    continue
                file.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='.transfer-', dir=file.parent) as temporary:
                    temporary = Path(temporary)
                    staging = temporary / 'files'; staging.mkdir()
                    for key in changed:
                        target = staging / key; target.parent.mkdir(parents=True, exist_ok=True)
                        target.symlink_to(sources[key])  # Staging references avoid copying large rasters.
                    index_file = temporary / 'archive-index.json'
                    atomic_json(index_file, index)
                    backend = BACKENDS[destination['backend']](destination)
                    backend.claim(project.id, temporary)
                    if changed:
                        backend.transfer(staging)
                    backend.commit(project.id, index_file)
                # Failed transfers/index writes never replace successful receipts.
                atomic_json(file, {'config_hash': config_hash(destination),
                                   'storage_hash': config_hash(destination, storage=True),
                                   'fingerprints': {**old_fingerprints, **fingerprints}, 'index': index})
            except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
                errors.append(f'{destination["id"]}: {error}')
        if errors:
            raise RuntimeError('Archive incomplete; successful destinations retained. ' + '; '.join(errors))


def download_index(project):
    sources, dates = [], []
    for destination in project.archive:
        _, previous = receipt(project, destination)
        if previous and destination.get('public_url'):
            sources.extend(previous['index']['sources'])
            dates.append(previous['index']['indexed_at'])
    return {'version': 2, 'project': {'id': project.id, 'name': project.name},
            'indexed_at': max(dates) if dates else None, 'sources': sources}


def publish_downloads(site, project, *, remote):
    index = download_index(project)
    root = site.staging / 'data' / project.id
    atomic_file(safe_path(root, 'downloads.json'), json.dumps(index).encode())
    if remote:
        destination = {**site.deploy, 'directory': str(PurePosixPath(site.deploy['directory']) / 'data' / project.id)}
        remote_helper(destination, 'downloads', project.id, json.dumps(index).encode())
