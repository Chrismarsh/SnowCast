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


def job_config(raw, base):
    keys(raw, ' '.join(JOB), 'job')
    job = merge(JOB, raw)
    if job['mode'] not in {'local', 'pbs'}:
        raise ValueError('job.mode must be local or pbs')
    for field in ('ranks', 'nodes', 'cpus_per_node', 'ranks_per_node', 'attempts'):
        positive(job[field], f'job.{field}', integer=True)
    for field in ('retry_delay_seconds', 'poll_seconds'):
        positive(job[field], f'job.{field}')
    if job['timeout_seconds'] is not None:
        positive(job['timeout_seconds'], 'job.timeout_seconds')
        if job['mode'] == 'pbs':
            raise ValueError('PBS jobs use walltime; timeout_seconds is for local execution')
    if not isinstance(job['retry_codes'], list) or any(type(c) is not int or c <= 0 for c in job['retry_codes']):
        raise ValueError('job.retry_codes must be nonzero integer exit codes')
    if not isinstance(job['launcher'], list) or any(not isinstance(s, str) or not s for s in job['launcher']):
        raise ValueError('job.launcher must be an argument list')
    if job['ranks'] > 1 and not job['launcher']:
        raise ValueError('Multiple ranks require a launcher, e.g. ["mpirun", "-n", "{ranks}"]')
    if job['mode'] == 'pbs' and (job['ranks'] != job['nodes'] * job['ranks_per_node'] or job['ranks_per_node'] > job['cpus_per_node']):
        raise ValueError('PBS ranks must match nodes × ranks_per_node and fit the CPU allocation')
    if not isinstance(job['walltime'], str) or not isinstance(job['memory'], str) or not re.fullmatch(r'\d+:\d{2}:\d{2}', job['walltime']) or not re.fullmatch(r'\d+(?:mb|gb)', job['memory']):
        raise ValueError('Invalid PBS walltime or memory')
    for field in ('qsub', 'qstat', 'queue'):
        if not isinstance(job[field], str) or not job[field] or '\n' in job[field]:
            raise ValueError(f'job.{field} must be a nonempty string')
    for field in ('qsub', 'qstat'):
        job[field] = executable(base, job[field])
    if job['launcher']:
        job['launcher'][0] = executable(base, job['launcher'][0])
    if job['setup']:
        job['setup'] = path(base, job['setup'])
    return job


@dataclass(frozen=True)
class Domain:
    id: str
    name: str
    work: Path
    model: dict
    forcing: dict
    postprocess: dict
    display: dict


@dataclass(frozen=True)
class Project:
    file: Path
    id: str
    work_root: Path
    domains: tuple[Domain, ...]
    notifications: dict

    def domain(self, identifier=None):
        if identifier is None and len(self.domains) == 1:
            return self.domains[0]
        for domain in self.domains:
            if domain.id == identifier:
                return domain
        raise ValueError(f'Select --domain from: {", ".join(d.id for d in self.domains)}')


def load_project(filename):
    filename = Path(filename).expanduser().resolve()
    if filename.is_dir():
        filename /= 'snowcast.json'
    raw = json.loads(filename.read_text())
    keys(raw, 'version id work_root defaults domains notifications', 'project')
    if type(raw.get('version')) is not int or raw['version'] != 1:
        raise ValueError('Unsupported project version; expected 1')
    identifier = slug(raw.get('id'), 'project.id')
    base = filename.parent
    root = path(base, raw.get('work_root', 'work'))
    if base == root or base.is_relative_to(root):
        raise ValueError('work_root must not contain the project definition')
    defaults = raw.get('defaults', {})
    notifications = raw.get('notifications', {})
    keys(notifications, 'webhook_env', 'notifications')
    if notifications and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', str(notifications.get('webhook_env', ''))):
        raise ValueError('notifications.webhook_env must name an environment variable')
    keys(defaults, 'model forcing postprocess display', 'defaults')
    if not isinstance(raw.get('domains'), list) or not raw['domains']:
        raise ValueError('A project requires at least one domain')
    domains = []
    for entry in raw['domains']:
        keys(entry, 'id name model forcing postprocess display', 'domain')
        d = merge(defaults, entry)
        did = slug(d.get('id'), 'domain.id')
        if 'name' in d and (not isinstance(d['name'], str) or not d['name'].strip()):
            raise ValueError('domain.name must be a nonempty string')
        if any(prior.id == did for prior in domains):
            raise ValueError(f'Duplicate domain ID: {did}')
        model = d.get('model', {})
        keys(model, 'config start_date command output_file max_runs checkpoint_keep_days no_data_codes assets job', f'{did}.model')
        model = merge({'command': ['CHM', '-f', '{config}'], 'output_file': 'output.nc', 'max_runs': 10,
                       'checkpoint_keep_days': 3, 'no_data_codes': [], 'assets': {}, 'job': {}}, model)
        model['config'] = path(base, model.get('config'))
        if model.get('start_date'):
            datetime.strptime(model['start_date'], '%Y-%m-%d')
        if not isinstance(model['output_file'], str) or not model['output_file'] or Path(model['output_file']).name != model['output_file']:
            raise ValueError('model.output_file must be a filename within the domain output directory')
        for field in ('max_runs', 'checkpoint_keep_days'):
            positive(model[field], f'model.{field}', integer=True)
        if not isinstance(model['no_data_codes'], list) or any(type(c) is not int or c <= 0 for c in model['no_data_codes']):
            raise ValueError('model.no_data_codes must list nonzero integer exit codes')
        if not isinstance(model['command'], list) or not model['command'] or any(not isinstance(s, str) or not s for s in model['command']):
            raise ValueError('model.command must be an argument list')
        model['command'][0] = executable(base, model['command'][0])
        model['job'] = job_config(model['job'], base)
        if not isinstance(model['assets'], dict):
            raise ValueError('model.assets must map workspace filenames to input paths')
        for name, source in model['assets'].items():
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
                raise ValueError('model.assets aliases must be simple filenames')
            if name in {'output', 'log', 'config', 'config.json', 'met'}:
                raise ValueError(f'Reserved model asset name: {name}')
            model['assets'][name] = path(base, source)
        forcing = d.get('forcing', {})
        keys(forcing, 'index glob', f'{did}.forcing')
        if len(forcing) != 1:
            raise ValueError('Provide exactly one forcing.index or forcing.glob')
        forcing = {k: path(base, v) for k, v in forcing.items()}
        pp = d.get('postprocess', {})
        keys(pp, 'variables source_resolution method recent_steps exporter mesh grid ascii job', f'{did}.postprocess')
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
        pp['job'] = job_config(pp['job'], base)
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
        display = d.get('display', {})
        keys(display, 'ranges', 'display')
        if not isinstance(display.get('ranges', {}), dict):
            raise ValueError('display.ranges must be an object')
        for var, span in display.get('ranges', {}).items():
            if var not in VARIABLES or not isinstance(span, list) or len(span) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in span) or span[0] >= span[1]:
                raise ValueError('display.ranges must map supported variables to increasing finite pairs')
        domains.append(Domain(did, d.get('name', did), root / did, model, forcing, pp, display))
    return Project(filename, identifier, root, tuple(domains), notifications)


def validate_inputs(project, domains=None):
    from rasterio.crs import CRS
    for d in project.domains if domains is None else domains:
        inputs = [d.model['config'], *d.model['assets'].values()]
        inputs += [job['setup'] for job in (d.model['job'], d.postprocess['job']) if job['setup']]
        if 'index' in d.forcing:
            inputs.append(d.forcing['index'])
        elif d.forcing['glob'].is_relative_to(project.work_root):
            raise ValueError('Forcing inputs must be outside work_root')
        if d.postprocess.get('mesh'):
            inputs.append(d.postprocess['mesh'])
        for source in inputs:
            if not source.exists():
                raise FileNotFoundError(f'{d.id}: input missing: {source}')
            if source.is_relative_to(project.work_root):
                raise ValueError(f'{d.id}: project inputs must be outside work_root: {source}')
        if not CRS.from_user_input(d.postprocess['grid']['crs']).to_epsg():
            raise ValueError(f'{d.id}: grid CRS must have an EPSG identifier')
