"""Convert cached observations and publish immutable station assets independently."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .cog_store import atomic_json, commit_observations, store_lock
from .observation_data import public_dataset, require_source
from .upload import _remote_store, _run_with_retry


def prepare_project(site, project):
    catalogue = json.loads((site.staging / 'data' / project.id / 'catalog.json').read_text())
    from .canswe import geographic_bounds, prepare
    domain = {'id': project.id, 'name': project.name,
              'bounds': geographic_bounds(catalogue.get('bounds'), project.id)}
    if catalogue.get('domain', {}).get('id') != project.id:
        raise ValueError('Observation selection catalogue has the wrong project identity')
    contributions = []
    errors = []
    # One per-dataset lock also protects netCDF4 (which is not thread-safe).
    for entry in site.observations:
        public = public_dataset(entry)
        signature = hashlib.sha256(json.dumps([public['revision'], domain], sort_keys=True).encode()).hexdigest()
        output = site.staging / 'observations' / entry['id']
        with store_lock(site.staging / '.observation-build'):
            try:
                source = require_source(entry, registry=site.observation_registry, cache=site.observation_cache)
                receipt = site.staging / '.observation-build' / f'{entry["id"]}-{project.id}.json'
                cached = json.loads(receipt.read_text()) if receipt.is_file() else {}
                if cached.get('signature') == signature and all(
                        (output / station['href']).is_file() for station in cached['index']['stations']):
                    index = cached['index']
                else:
                    with tempfile.TemporaryDirectory(prefix='snowcast-observations-') as tmp:
                        temporary = Path(tmp)
                        # Adapters produce the documented common snow-stations-v1 format.
                        index = prepare(source, temporary, domains=[domain], entry=entry)
                        for station in index['stations']:
                            target = output / station['href']
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                                pending = Path(stream.name)
                                try:
                                    with (temporary / station['href']).open('rb') as incoming:
                                        shutil.copyfileobj(incoming, stream)
                                    stream.flush()
                                    pending.chmod(0o644)
                                    pending.replace(target)
                                finally:
                                    pending.unlink(missing_ok=True)
                            for directory in (output, target.parent, output.parent):
                                directory.chmod(0o755)
                        atomic_json(receipt, {'signature': signature, 'index': index})
                contributions.append({'id': entry['id'], 'revision': public['revision'], 'index': index})
            except (ValueError, OSError, RuntimeError) as error:
                errors.append(str(error))
    payload = {'spec': site.spec, 'project': project.id, 'datasets': contributions}
    # Even an empty selection can remove disabled datasets from the manifest.
    commit_observations(site.staging, payload)
    return payload, errors


def upload_observations(site, payload):
    paths = sorted({f'observations/{entry["id"]}/{s["href"]}'
                    for entry in payload['datasets'] for s in entry['index']['stations']})
    if paths:
        with tempfile.TemporaryDirectory(prefix='snowcast-observation-upload-') as tmp:
            listing = Path(tmp) / 'files.txt'
            listing.write_text('\n'.join(paths) + '\n')
            _run_with_retry(['rsync', '-rtp', '--chmod=D755,F644', '--protect-args',
                             f'--files-from={listing}', f'{site.staging}/',
                             f'{site.deploy["host"]}:{site.deploy["directory"]}/'])
    # Host merges this project's selection with the latest other projects.
    # Histories are verified before indexes, then the public registry commits last.
    _run_with_retry(_remote_store(site.deploy['host'], site.deploy['directory'],
                                 'commit-observations', payload['project']),
                    input=json.dumps(payload).encode())
