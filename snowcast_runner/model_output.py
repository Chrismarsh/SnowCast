"""Keep CHM's configured and checkpoint-restored output in the project workspace."""
import json
from pathlib import Path

from .progress import progress


def configure_output(project, config):
    """Configure the same fixed NetCDF that postprocessing reads."""
    filename = Path(project.model['output_file'])
    if filename.suffix != '.nc':
        raise ValueError('model.output_file must be a .nc filename for CHM NetCDF output')
    output = config.setdefault('output', {})
    output['output_dir'] = 'output'
    ugrid = output.setdefault('ugrid', {})
    if ugrid.get('format', 'netcdf') not in ('netcdf', 'nc'):
        raise ValueError('SnowCast postprocessing requires CHM output.ugrid.format=netcdf')
    if ugrid.get('rotate_frequency') is not None:
        raise ValueError('CHM output.ugrid.rotate_frequency is not supported by the fixed-file postprocessor; '
                         'remove it and consolidate any existing rotated output before continuing')
    ugrid['base_name'] = filename.stem
    ugrid['variables'] = project.postprocess['variables']


def validate_output(cwd, filename, config, *, postprocessing=False):
    """Fail before launching CHM or accepting rasters from a different output file.

    Checkpoint paths are relative to CHM's working directory, not the JSON's
    parent. Match the UGRID entry using CHM's base-name/single-entry rules.
    Never rewrite checkpoints or follow their output into another workspace.
    """
    cwd = Path(cwd)
    expected = cwd / 'output' / filename
    if expected.resolve() != expected or expected.is_symlink():
        raise ValueError(f'CHM output must be a project-owned file, not a symlink: {expected}')
    output = config.get('output', {})
    directory = output.get('output_dir', 'output')
    ugrid = output.get('ugrid', {})
    base_name = ugrid.get('base_name', directory)
    configured = (cwd / directory / (base_name + '.nc')).resolve()
    if configured != expected or ugrid.get('format', 'netcdf') not in ('netcdf', 'nc'):
        raise ValueError(f'CHM output configuration points to {configured}; SnowCast reads {expected}. '
                         'Run snowcast prepare PROJECT to regenerate the output configuration.')
    if ugrid.get('rotate_frequency') is not None:
        raise ValueError('CHM output rotation is not supported by the fixed-file postprocessor; '
                         'consolidate the output and remove output.ugrid.rotate_frequency')

    options = config.get('checkpoint', {})
    checkpoints = []
    explicit = options.get('load_checkpoint_path')
    if explicit:
        checkpoints.append((cwd / explicit).resolve())
    if postprocessing or str(options.get('auto_resume', False)).lower() == 'true':
        available = sorted((cwd / 'output/checkpoint').glob('checkpoint_*.json'))
        if available:
            checkpoints.append(available[-1])
    for checkpoint in dict.fromkeys(checkpoints):
        record = json.loads(checkpoint.read_text())
        if not isinstance(record, dict):
            raise ValueError(f'Invalid checkpoint object: {checkpoint}')
        entries = record.get('ugrid_outputs', [])
        if not isinstance(entries, list) or any(
                not isinstance(entry, dict) or not isinstance(entry.get('base_name', ''), str)
                or not isinstance(entry.get('path', ''), str) for entry in entries):
            raise ValueError(f'Invalid ugrid_outputs in checkpoint: {checkpoint}')
        match = next((entry for entry in entries if entry.get('base_name') == base_name), None)
        if match is None and len(entries) == 1:
            match = entries[0]
        if match is None or not match.get('path'):
            continue
        actual = (cwd / match['path']).resolve()
        if actual != expected:
            raise ValueError(f'Checkpoint {checkpoint} restores CHM UGRID output to {actual}, '
                             f'but SnowCast reads {expected}. Stop both writers, copy the updated NetCDF '
                             'into this project, then back up and correct the project checkpoint\'s '
                             'ugrid_outputs path. Do not replace the NetCDF with a symlink. '
                             'See projects/README.md: Recovering output written to a legacy workspace.')
    progress(f'CHM output target verified: {expected}')
    return expected


def postprocess_source(project):
    from .chm_config import read_model

    cwd = project.work / 'chm'
    staged = cwd / 'config.json'
    if staged.exists():
        config = json.loads(staged.read_text())
    else:
        config = read_model(project)
        configure_output(project, config)
    return validate_output(cwd, project.model['output_file'], config, postprocessing=True)
