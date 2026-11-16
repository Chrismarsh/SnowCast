"""Versioned, declarative projects; paths are relative to the project file."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re

SLUG = re.compile(r'[a-z][a-z0-9_-]{0,63}\Z')
VARIABLES = {'swe', 'snowdepthavg', 't'}
MODEL_RESERVED_NAMES = {'output', 'log', 'config', 'config.json', 'met'}


def merge(base, overrides):
    result = deepcopy(base)
    for key, value in overrides.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else deepcopy(value)
    return result


def keys(value, allowed, where):
    if not isinstance(value, dict):
        raise ValueError(f'{where} must be an object')
    unknown = set(value) - set(allowed.split())
    if unknown:
        raise ValueError(f'{where}: unknown settings {sorted(unknown)}')


def positive(value, name, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be positive')
    if integer and not isinstance(value, int):
        raise ValueError(f'{name} must be an integer')


def slug(value, name):
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        raise ValueError(f'{name} must be a lowercase ID using letters, digits, underscores or hyphens')
    return value


def path(base, value):
    if not isinstance(value, str) or not value or '\0' in value:
        raise ValueError('Paths must be nonempty strings')
    p = Path(value).expanduser()
    return (base / p).resolve()


def executable(base, value):
    # Resolving a venv's python symlink selects the system interpreter and loses
    # its installed dependencies. Absolutize executable paths without dereferencing.
    return os.path.abspath(base / Path(value).expanduser()) if '/' in value else value


def variables(value, name):
    if not isinstance(value, list) or not value or any(v not in VARIABLES for v in value) or len(set(value)) != len(value):
        raise ValueError(f'{name} must list unique supported variables: {sorted(VARIABLES)}')


JOB = {'mode': 'local', 'ranks': 1, 'launcher': [], 'setup': None, 'timeout_seconds': None,
       'attempts': 1, 'retry_codes': [], 'retry_delay_seconds': 30,
       'queue': 'development', 'nodes': 1, 'cpus_per_node': 1, 'ranks_per_node': 1,
       'memory': '4gb', 'walltime': '01:00:00', 'qsub': 'qsub', 'qstat': 'qstat', 'poll_seconds': 15}


def job_config(raw, base, *, where='job'):
    keys(raw, ' '.join(JOB), where)
    job = merge(JOB, raw)
    if job['mode'] not in {'local', 'pbs'}:
        raise ValueError(f'{where}.mode must be local or pbs')
    for field in ('ranks', 'nodes', 'cpus_per_node', 'ranks_per_node', 'attempts'):
        positive(job[field], f'{where}.{field}', integer=True)
    for field in ('retry_delay_seconds', 'poll_seconds'):
        positive(job[field], f'{where}.{field}')
    if job['timeout_seconds'] is not None:
        positive(job['timeout_seconds'], f'{where}.timeout_seconds')
        if job['mode'] == 'pbs':
            raise ValueError(f'{where}: PBS jobs use walltime; timeout_seconds is for local execution')
    if not isinstance(job['retry_codes'], list) or any(type(c) is not int or c <= 0 for c in job['retry_codes']):
        raise ValueError(f'{where}.retry_codes must be nonzero integer exit codes')
    if not isinstance(job['launcher'], list) or any(not isinstance(s, str) or not s for s in job['launcher']):
        raise ValueError(f'{where}.launcher must be an argument list')
    if job['ranks'] > 1 and not job['launcher']:
        raise ValueError(f'{where}: Multiple ranks require a launcher, e.g. ["mpirun", "-n", "{{ranks}}"]')
    if job['mode'] == 'pbs':
        allocated = job['nodes'] * job['ranks_per_node']
        if job['ranks'] != allocated:
            raise ValueError(f'{where}: ranks={job["ranks"]} must equal '
                             f'nodes={job["nodes"]} × ranks_per_node={job["ranks_per_node"]} ({allocated})')
        if job['ranks_per_node'] > job['cpus_per_node']:
            raise ValueError(f'{where}: ranks_per_node={job["ranks_per_node"]} '
                             f'exceeds cpus_per_node={job["cpus_per_node"]}')
    if not isinstance(job['walltime'], str) or not isinstance(job['memory'], str) or not re.fullmatch(r'\d+:\d{2}:\d{2}', job['walltime']) or not re.fullmatch(r'\d+(?:mb|gb)', job['memory']):
        raise ValueError(f'{where}: Invalid PBS walltime or memory')
    for field in ('qsub', 'qstat', 'queue'):
        if not isinstance(job[field], str) or not job[field] or '\n' in job[field]:
            raise ValueError(f'{where}.{field} must be a nonempty string')
    for field in ('qsub', 'qstat'):
        job[field] = executable(base, job[field])
    if job['launcher']:
        job['launcher'][0] = executable(base, job['launcher'][0])
    if job['setup']:
        try:
            job['setup'] = path(base, job['setup'])
        except ValueError as error:
            raise ValueError(f'{where}.setup: {error}') from error
    return job


@dataclass(frozen=True)
class Project:
    file: Path
    id: str
    name: str
    work: Path
    model: dict
    forcing: dict
    postprocess: dict
    display: dict
    notifications: dict
    archive: list


def load_project(filename):
    filename = Path(filename).expanduser().resolve()
    if filename.is_dir():
        filename /= 'snowcast.json'
    raw = json.loads(filename.read_text())
    if isinstance(raw, dict) and (raw.get('version') == 1 or 'domains' in raw or 'defaults' in raw):
        raise ValueError('Project version 1 used nested domains. Create a version 2 project folder per domain; '
                         'see projects/README.md for migration. Existing work is not moved automatically.')
    keys(raw, 'version id name model forcing postprocess display notifications archive', 'project')
    if type(raw.get('version')) is not int or raw['version'] != 2:
        raise ValueError('Unsupported project version; expected 2')
    identifier = slug(raw.get('id'), 'project.id')
    display_name = raw.get('name', identifier)
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError('project.name must be a nonempty string')
    base = filename.parent
    work = base / 'work'
    if work.is_symlink():
        raise ValueError('Project work directory cannot be a symlink; place the project folder on the desired filesystem')
    notifications = raw.get('notifications', {})
    keys(notifications, 'webhook_env', 'notifications')
    if notifications and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', str(notifications.get('webhook_env', ''))):
        raise ValueError('notifications.webhook_env must name an environment variable')
    model = raw.get('model', {})
    keys(model, 'config overrides remove start_date command output_file max_runs checkpoint_keep_days no_data_codes assets job', f'{identifier}.model')
    model = merge({'command': ['CHM', '-f', '{config}'], 'output_file': 'output.nc', 'max_runs': 10,
                   'checkpoint_keep_days': 3, 'no_data_codes': [], 'assets': {}, 'job': {}}, model)
    model['config'] = path(base, model.get('config'))
    if model.get('overrides') is not None:
        model['overrides'] = path(base, model['overrides'])
    removals = model.setdefault('remove', [])
    if not isinstance(removals, list) or any(not isinstance(item, str) or not item.startswith('/') or
                                           re.search(r'~(?![01])', item) for item in removals):
        raise ValueError('model.remove must list JSON pointers, e.g. /config/unused_module')
    if model.get('start_date') is not None:
        if not isinstance(model['start_date'], str):
            raise ValueError('model.start_date must be YYYY-MM-DD')
        model['start_date'] = datetime.strptime(model['start_date'], '%Y-%m-%d').strftime('%Y-%m-%d')
    if not isinstance(model['output_file'], str) or not model['output_file'] or Path(model['output_file']).name != model['output_file']:
        raise ValueError('model.output_file must be a filename within the project output directory')
    for field in ('max_runs', 'checkpoint_keep_days'):
        positive(model[field], f'model.{field}', integer=True)
    if not isinstance(model['no_data_codes'], list) or any(type(c) is not int or c <= 0 for c in model['no_data_codes']):
        raise ValueError('model.no_data_codes must list nonzero integer exit codes')
    if not isinstance(model['command'], list) or not model['command'] or any(not isinstance(s, str) or not s for s in model['command']):
        raise ValueError('model.command must be an argument list')
    model['command'][0] = executable(base, model['command'][0])
    model['job'] = job_config(model['job'], base, where='model.job')
    if not isinstance(model['assets'], dict):
        raise ValueError('model.assets must map workspace filenames to input paths')
    for name, source in model['assets'].items():
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
            raise ValueError('model.assets aliases must be simple filenames')
        if name in MODEL_RESERVED_NAMES:
            raise ValueError(f'Reserved model asset name: {name}')
        model['assets'][name] = path(base, source)
    forcing = raw.get('forcing', {})
    keys(forcing, 'index archive', f'{identifier}.forcing')
    archive = path(base, forcing['archive']) if forcing.get('archive') is not None else None
    managed_index = forcing.get('index') is None
    if archive is None and managed_index:
        raise ValueError('Provide forcing.archive (NetCDF directory) or forcing.index (existing CHM metadata JSON)')
    forcing = {'archive': archive, 'managed_index': managed_index,
               'index': work / 'met' / 'metadata.json' if managed_index else path(base, forcing['index'])}
    pp = raw.get('postprocess', {})
    keys(pp, 'variables source_resolution method recent_steps exporter mesh grid ascii job', f'{identifier}.postprocess')
    pp = merge({'variables': ['swe', 'snowdepthavg', 't'], 'source_resolution': 0.001,
                'method': 'conservative', 'recent_steps': 2, 'exporter': 'chm_ugrid2grid',
                'grid': {}, 'ascii': {'enabled': False}, 'job': {}}, pp)
    variables(pp['variables'], 'postprocess.variables')
    positive(pp['source_resolution'], 'postprocess.source_resolution')
    positive(pp['recent_steps'], 'postprocess.recent_steps', integer=True)
    if pp['method'] not in ('conservative', 'bilinear'):
        raise ValueError('postprocess.method must be conservative or bilinear')
    if not isinstance(pp['exporter'], str) or not pp['exporter']:
        raise ValueError('postprocess.exporter must name an executable')
    pp['exporter'] = executable(base, pp['exporter'])
    if pp.get('mesh'):
        pp['mesh'] = path(base, pp['mesh'])
    pp['job'] = job_config(pp['job'], base, where='postprocess.job')
    keys(pp['grid'], 'crs resolution bounds resampling', 'postprocess.grid')
    grid = merge({'crs': 'EPSG:4326', 'resolution': [pp['source_resolution']] * 2,
                  'bounds': None, 'resampling': 'nearest'}, pp['grid'])
    if not isinstance(grid['resolution'], list) or len(grid['resolution']) != 2:
        raise ValueError('grid.resolution must be [x_spacing, y_spacing] in target CRS units')
    for v in grid['resolution']:
        positive(v, 'grid.resolution')
    bounds = grid['bounds']
    if bounds is not None and (not isinstance(bounds, list) or len(bounds) != 4 or
                              any(type(v) not in (int, float) or not math.isfinite(v) for v in bounds) or
                              bounds[0] >= bounds[2] or bounds[1] >= bounds[3]):
        raise ValueError('grid.bounds must be [west, south, east, north] in target CRS units')
    if grid['resampling'] not in ('nearest', 'bilinear', 'average'):
        raise ValueError('grid.resampling must be nearest, bilinear or average')
    pp['grid'] = grid
    keys(pp['ascii'], 'enabled variables resolution', 'postprocess.ascii')
    pp['ascii'] = merge({'enabled': False, 'variables': ['swe', 't'], 'resolution': 0.036}, pp['ascii'])
    if type(pp['ascii']['enabled']) is not bool:
        raise ValueError('ascii.enabled must be true or false')
    variables(pp['ascii']['variables'], 'ascii.variables')
    positive(pp['ascii']['resolution'], 'ascii.resolution')
    if pp['ascii']['enabled'] and not set(pp['ascii']['variables']) <= set(pp['variables']):
        raise ValueError('ASCII variables must be included in postprocess.variables')
    display = raw.get('display', {})
    keys(display, 'ranges', 'display')
    if not isinstance(display.get('ranges', {}), dict):
        raise ValueError('display.ranges must be an object')
    for var, span in display.get('ranges', {}).items():
        if var not in VARIABLES or not isinstance(span, list) or len(span) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in span) or span[0] >= span[1]:
            raise ValueError('display.ranges must map supported variables to increasing finite pairs')
    from .archive import destinations
    archive = destinations(raw.get('archive', {}), base, identifier, work)
    return Project(filename, identifier, display_name, work, model, forcing, pp, display, notifications, archive)


def validate_forcing(project):
    index, archive = project.forcing['index'], project.forcing.get('archive')
    inputs = [archive] if project.forcing['managed_index'] else [index, archive]
    for source in inputs:
        if source is not None and source.is_relative_to(project.work):
            raise ValueError(f'{project.id}: forcing inputs must be outside work/: {source}')
    if archive is not None and not archive.is_dir():
        raise FileNotFoundError(f'{project.id}: forcing archive directory missing: {archive}')
    if project.forcing['managed_index'] and index.is_symlink():
        raise ValueError(f'{project.id}: managed forcing metadata cannot be a symlink: {index}')
    if index.is_dir():
        raise ValueError(f'{project.id}: forcing.index is a directory; set forcing.archive to the NetCDF directory instead: {index}')
    if (index.exists() or archive is None) and not index.is_file():
        raise FileNotFoundError(f'{project.id}: forcing metadata file missing or invalid: {index}')


def validate_inputs(project):
    from rasterio.crs import CRS
    validate_forcing(project)
    inputs = [project.model['config'], *project.model['assets'].values()]
    if project.model.get('overrides'):
        inputs.append(project.model['overrides'])
    inputs += [job['setup'] for job in (project.model['job'], project.postprocess['job']) if job['setup']]
    if project.postprocess.get('mesh'):
        inputs.append(project.postprocess['mesh'])
    for source in inputs:
        if not source.exists():
            raise FileNotFoundError(f'{project.id}: input missing: {source}')
        if source.is_relative_to(project.work):
            raise ValueError(f'{project.id}: project inputs must be outside work/: {source}')
    if not CRS.from_user_input(project.postprocess['grid']['crs']).to_epsg():
        raise ValueError(f'{project.id}: grid CRS must have an EPSG identifier')
