"""CHM adapter: resolve inputs, stage forcing metadata, and continue checkpointed runs."""
import re
import shutil
import uuid
from pathlib import Path

from .cog_store import atomic_json
from .jobs import execute, JobFailed
from .forcing import forcing_index

from .chm_config import read_model, model_inputs


def prepare(project):
    config = read_model(project)
    links = model_inputs(project, config)
    cwd = project.work / 'chm'
    cwd.mkdir(exist_ok=True)
    output = cwd / 'output'
    output.mkdir(exist_ok=True)
    for name, source in links.items():
        target = cwd / name
        if target.is_symlink():  # model_inputs already checked its destination.
            continue
        target.symlink_to(source, target_is_directory=source.is_dir())
    config['meshes'] = {key: Path(value).name for key, value in config['meshes'].items()}
    index, end = forcing_index(project)
    config.setdefault('forcing', {})['file'] = str(index)
    config.setdefault('output', {})['output_dir'] = str(output)
    config['output'].setdefault('ugrid', {})['variables'] = project.postprocess['variables']
    if project.model.get('start_date'):
        config.setdefault('option', {})['startdate'] = project.model['start_date'].replace('-', '') + 'T000000'
    checkpoints = sorted((output / 'checkpoint').glob('checkpoint_*.json'))
    for checkpoint in checkpoints:
        for count in re.findall(r'\.np(\d+)', checkpoint.name):
            if int(count) != project.model['job']['ranks']:
                raise ValueError(f'Checkpoint ranks do not match configured ranks: {checkpoint}')
    target = cwd / 'config.json'
    atomic_json(target, config)
    return target, end, checkpoints


def prune_checkpoints(project):
    folder = project.work / 'chm' / 'output' / 'checkpoint'
    if folder.is_symlink():
        raise ValueError('Checkpoint directory cannot be a symlink')
    checkpoints = sorted(folder.glob('checkpoint_*.json'))
    # Group by date; multiple wallclock checkpoints on one day count as one day.
    dates = sorted({p.name.removeprefix('checkpoint_')[:8] for p in checkpoints})
    keep = set(dates[-project.model['checkpoint_keep_days']:])
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


def run_model(project):
    config, forcing_end, checkpoints = prepare(project)
    if checkpoints:
        stamp = re.search(r'checkpoint_(\d{8}T\d{6})', checkpoints[-1].name)
        if stamp and stamp[1] >= forcing_end:
            return 'up_to_date'
    cwd = config.parent
    clean_exit = cwd / 'output' / 'clean_exit'
    clean_exit.unlink(missing_ok=True)
    for segment in range(project.model['max_runs']):
        checkpoint_dir = cwd / 'output' / 'checkpoint'
        before = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in checkpoint_dir.glob('checkpoint_*.json')}
        # Preserve model logs per segment; an old exception must not mark a new run failed.
        old_log = cwd / 'log'
        if old_log.exists():
            destination = project.work / 'jobs' / f'previous-chm-log-{uuid.uuid4().hex[:12]}'
            destination.parent.mkdir(exist_ok=True)
            old_log.rename(destination)
        command = [part.replace('{config}', str(config)) for part in project.model['command']]
        code, log = execute(command, work=project.work, cwd=cwd, job=project.model['job'], label=f'{project.id}-chm',
                            accepted_codes=[0, *project.model['no_data_codes']])
        if code in project.model['no_data_codes']:
            return 'up_to_date'
        if code:
            raise JobFailed(f'{project.id}: CHM exit {code}; see {log}')
        if clean_exit.is_file():
            prune_checkpoints(project)
            return 'completed'
        after = {p.name: (p.stat().st_mtime_ns, p.stat().st_size) for p in checkpoint_dir.glob('checkpoint_*.json')}
        if after == before:
            raise JobFailed(f'{project.id}: CHM exited without clean_exit or a new checkpoint; see {log}')
    raise JobFailed(f'{project.id}: CHM did not produce clean_exit after {project.model["max_runs"]} segments')
