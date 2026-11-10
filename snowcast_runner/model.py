"""CHM adapter: resolve inputs, stage forcing metadata, and continue checkpointed runs."""
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import uuid

from postprocess.cog_store import atomic_json
from .jobs import execute, JobFailed


def read_model(domain):
    import json5
    config = json5.loads(domain.model['config'].read_text())
    if not isinstance(config, dict) or not isinstance(config.get('meshes'), dict):
        raise ValueError('CHM configuration requires a meshes object')
    return config


def model_inputs(domain, config):
    # Relative mesh references have the same meaning after staging the template.
    for key, value in config['meshes'].items():
        if not isinstance(value, str):
            raise ValueError(f'CHM meshes.{key} must be a path')
        source = (domain.model['config'].parent / value).resolve()
        if not source.is_file():
            raise FileNotFoundError(f'Mesh input missing: {source}')
        for count in re.findall(r'\.np(\d+)', source.name):
            if int(count) != domain.model['job']['ranks']:
                raise ValueError(f'Mesh partition ranks do not match configured ranks: {source}')
        config['meshes'][key] = str(source)


def forcing_index(domain):
    # The upstream CHM metadata is authoritative; never rediscover NetCDF files
    # or recompute their time ranges. Snapshot it so a later upstream update
    # cannot change the forcing list of an already submitted job.
    source = domain.forcing['index']
    records = json.loads(source.read_text())
    if not isinstance(records, list):
        raise ValueError('Forcing index must be a list')
    if not records:
        raise ValueError(f'No forcing available for {domain.id}')
    for row in records:
        row['file_name'] = str((source.parent / row['file_name']).resolve())
        start, end = [datetime.strptime(row[k], '%Y%m%dT%H%M%S') for k in ('start_time', 'end_time')]
        if start > end or not Path(row['file_name']).is_file():
            raise ValueError(f'Invalid forcing interval/file: {row}')
    target = domain.work / 'met' / 'index.json'
    atomic_json(target, records)
    return target, max(row['end_time'] for row in records)


def prepare(domain):
    config = read_model(domain)
    model_inputs(domain, config)
    cwd = domain.work / 'chm'
    cwd.mkdir(exist_ok=True)
    output = cwd / 'output'
    output.mkdir(exist_ok=True)
    for name, source in domain.model['assets'].items():
        if name in {'output', 'log', 'config', 'config.json', 'met'}:
            raise ValueError(f'Reserved model asset name: {name}')
        target = cwd / name
        if target.is_symlink() and target.resolve() == source:
            continue
        if target.exists() or target.is_symlink():
            raise ValueError(f'Model asset destination already exists: {target}')
        target.symlink_to(source, target_is_directory=source.is_dir())
    index, end = forcing_index(domain)
    config.setdefault('forcing', {})['file'] = str(index)
    config.setdefault('output', {})['output_dir'] = str(output)
    config['output'].setdefault('ugrid', {})['variables'] = domain.postprocess['variables']
    if domain.model.get('start_date'):
        config.setdefault('option', {})['startdate'] = domain.model['start_date'].replace('-', '') + 'T000000'
    checkpoints = sorted((output / 'checkpoint').glob('checkpoint_*.json'))
    for checkpoint in checkpoints:
        for count in re.findall(r'\.np(\d+)', checkpoint.name):
            if int(count) != domain.model['job']['ranks']:
                raise ValueError(f'Checkpoint ranks do not match configured ranks: {checkpoint}')
    target = cwd / 'config.json'
    atomic_json(target, config)
    return target, end, checkpoints


def prune_checkpoints(domain):
    folder = domain.work / 'chm' / 'output' / 'checkpoint'
    if folder.is_symlink():
        raise ValueError('Checkpoint directory cannot be a symlink')
    checkpoints = sorted(folder.glob('checkpoint_*.json'))
    # Group by date; multiple wallclock checkpoints on one day count as one day.
    dates = sorted({p.name.removeprefix('checkpoint_')[:8] for p in checkpoints})
    keep = set(dates[-domain.model['checkpoint_keep_days']:])
    for p in checkpoints:
        match = re.fullmatch(r'checkpoint_(\d{8}T\d{6})(?:\.np\d+)?\.json', p.name)
        if not match or match[1][:8] in keep or p.is_symlink():
            continue
        state = folder / match[1]
        if state.is_symlink():
            raise ValueError(f'Refusing to prune symlink checkpoint: {state}')
        if state.is_dir():
            shutil.rmtree(state)
        p.unlink()


def run_model(domain):
    config, forcing_end, checkpoints = prepare(domain)
    if checkpoints:
        stamp = re.search(r'checkpoint_(\d{8}T\d{6})', checkpoints[-1].name)
        if stamp and stamp[1] >= forcing_end:
            return 'up_to_date'
    cwd = config.parent
    clean_exit = cwd / 'output' / 'clean_exit'
    clean_exit.unlink(missing_ok=True)
    for segment in range(domain.model['max_runs']):
        checkpoint_dir = cwd / 'output' / 'checkpoint'
        before = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in checkpoint_dir.glob('checkpoint_*.json')}
        # Preserve model logs per segment; an old exception must not mark a new run failed.
        old_log = cwd / 'log'
        if old_log.exists():
            destination = domain.work / 'jobs' / f'previous-chm-log-{uuid.uuid4().hex[:12]}'
            destination.parent.mkdir(exist_ok=True)
            old_log.rename(destination)
        command = [part.replace('{config}', str(config)) for part in domain.model['command']]
        code, log = execute(command, work=domain.work, cwd=cwd, job=domain.model['job'], label=f'{domain.id}-chm',
                            accepted_codes=[0, *domain.model['no_data_codes']])
        if code in domain.model['no_data_codes']:
            return 'up_to_date'
        if code:
            raise JobFailed(f'{domain.id}: CHM exit {code}; see {log}')
        if clean_exit.is_file():
            prune_checkpoints(domain)
            return 'completed'
        after = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in checkpoint_dir.glob('checkpoint_*.json')}
        if after == before:
            raise JobFailed(f'{domain.id}: CHM exited without clean_exit or a new checkpoint; see {log}')
    raise JobFailed(f'{domain.id}: CHM did not produce clean_exit after {domain.model["max_runs"]} segments')
