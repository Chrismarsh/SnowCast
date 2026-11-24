"""Authored observation registry and explicitly populated, verified source cache."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import tempfile
from urllib.request import Request, urlopen

from .cog_store import store_lock

DEFAULT_REGISTRY = Path(__file__).with_name('observations.json')
CONVERTER_VERSION = 1  # Bump whenever the common output or converter changes.


def load_registry(filename=None):
    registry = json.loads(Path(filename or DEFAULT_REGISTRY).read_text())
    if registry.get('version') != 1 or not isinstance(registry.get('datasets'), list):
        raise ValueError('Observation registry requires version 1 and datasets')
    ids = set()
    for entry in registry['datasets']:
        identity = entry.get('id')
        if not isinstance(identity, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', identity) or identity in ids:
            raise ValueError('Invalid or duplicate observation dataset ID')
        ids.add(identity)
        for key in ('label', 'description', 'adapter', 'renderer', 'release'):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(f'{identity}: missing {key}')
        if type(entry.get('enabled')) is not bool:
            raise ValueError(f'{identity}: enabled must be true or false')
        if entry['adapter'] != 'canswe' or entry['renderer'] != 'snow-stations-v1':
            raise ValueError(f'{identity}: unsupported adapter/renderer; add its implementation first')
        source = entry.get('source', {})
        if not isinstance(source.get('url'), str) or not source['url'].startswith('https://'):
            raise ValueError(f'{identity}: source.url must use HTTPS')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', source.get('filename', '')):
            raise ValueError(f'{identity}: unsafe source filename')
        if not re.fullmatch(r'(md5:[0-9a-f]{32}|sha256:[0-9a-f]{64})', source.get('checksum', '')):
            raise ValueError(f'{identity}: source.checksum must pin md5 or sha256')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', entry['release']):
            raise ValueError(f'{identity}: unsafe release')
        radius = entry.get('selection', {}).get('nearby_km')
        if type(radius) not in (int, float) or not math.isfinite(radius) or radius < 0:
            raise ValueError(f'{identity}: nearby_km must be finite and nonnegative')
        variables = entry.get('variables')
        if not isinstance(variables, dict) or not variables or any(
                {'swe': 'mm', 'depth': 'm'}.get(k) != v for k, v in variables.items()):
            raise ValueError(f'{identity}: snow-stations-v1 supports swe (mm) and depth (m)')
        metadata = entry.get('metadata', {})
        for key in ('doi', 'through', 'citation', 'licence', 'licence_url'):
            if not isinstance(metadata.get(key), str) or not metadata[key].strip():
                raise ValueError(f'{identity}: missing metadata.{key}')
        if any(not isinstance(metadata[key], str) or not metadata[key].startswith('https://')
               for key in ('doi', 'licence_url', *(['methods_url'] if 'methods_url' in metadata else []))):
            raise ValueError(f'{identity}: metadata links must use HTTPS')
    return registry


def public_dataset(entry):
    # Only public display metadata. Never publish cache paths or acquisition URLs.
    revision = hashlib.sha256(json.dumps([CONVERTER_VERSION, entry], sort_keys=True).encode()).hexdigest()
    return {**{key: entry[key] for key in ('id', 'label', 'description', 'renderer', 'variables', 'release')},
            **{k: v for k, v in entry['metadata'].items()
               if k in ('doi', 'through', 'citation', 'licence', 'licence_url', 'methods_url')},
            'revision': revision}


def cache_root(value=None):
    return Path(value or os.environ.get('SNOWCAST_DATA_CACHE') or
                Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'snowcast' / 'data').expanduser().resolve()


def source_path(entry, cache=None):
    # A registry change cannot silently reinterpret a previously cached release.
    return cache_root(cache) / entry['id'] / entry['release'] / entry['source']['checksum'].replace(':', '-') / entry['source']['filename']


def verify_source(path, entry):
    algorithm, expected = entry['source']['checksum'].split(':')
    digest = hashlib.new(algorithm)
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f'{entry["id"]}: source checksum does not match pinned {entry["release"]}')


def download_data(identity, *, registry=None, cache=None, source=None):
    entries = load_registry(registry)['datasets']
    entry = next((d for d in entries if d['id'] == identity), None)
    if entry is None:
        raise ValueError(f'Unknown observation dataset {identity}; available: {", ".join(d["id"] for d in entries)}')
    destination = source_path(entry, cache)
    with store_lock(destination.parent):
        if destination.is_file():
            try:
                verify_source(destination, entry)
            except ValueError:
                pass  # Replace corrupt cache only after its replacement is verified.
            else:
                print(f'{identity}: verified source already cached at {destination}')
                return destination
        fd, temporary = tempfile.mkstemp(prefix='.download-', dir=destination.parent)
        temporary = Path(temporary)
        try:
            with os.fdopen(fd, 'wb') as output:
                if source is not None:
                    incoming = Path(source).expanduser().open('rb')
                else:
                    print(f'{identity}: downloading pinned {entry["release"]}', flush=True)
                    incoming = urlopen(Request(entry['source']['url'], headers={'User-Agent': 'SnowCast/0.3'}), timeout=60)
                with incoming:
                    shutil.copyfileobj(incoming, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            verify_source(temporary, entry)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    print(f'{identity}: cached verified source at {destination}')
    return destination


def require_source(entry, *, registry=None, cache=None):
    location = source_path(entry, cache)
    command = f'snowcast download-data {entry["id"]}'
    if registry:
        command += f' --registry {shlex.quote(str(registry))}'
    if cache:
        command += f' --cache {shlex.quote(str(cache))}'
    try:
        verify_source(location, entry)
    except (OSError, ValueError) as error:
        raise ValueError(f'{entry["id"]}: no valid cached source. Run: {command}') from error
    return location
