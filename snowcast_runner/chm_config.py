"""Resolve authored CHM configurations before creating any run files."""
from pathlib import Path
import re

import json5

from .project import merge


def _read(source, project_id):
    try:
        value = json5.loads(source.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f'{project_id}: cannot read CHM configuration {source}: {error}') from error
    if not isinstance(value, dict):
        raise ValueError(f'{project_id}: CHM configuration must be an object: {source}')
    return value


def _origins(value, source, prefix=()):
    result = {prefix: source}
    if isinstance(value, dict):
        for key, child in value.items():
            result.update(_origins(child, source, (*prefix, key)))
    return result


def read_model(project):
    """Merge objects, replace lists/scalars, remove explicit keys, resolve meshes.

    Only known CHM input fields are interpreted as paths. Module-specific input
    files can be supplied through model.assets (stable aliases in the run cwd).
    Authored files are never rewritten.
    """
    base = project.model['config']
    config = _read(base, project.id)
    origins = _origins(config, base)
    override = project.model.get('overrides')
    if override is not None:
        fragment = _read(override, project.id)
        config = merge(config, fragment)
        origins.update(_origins(fragment, override))
    for pointer in project.model['remove']:
        keys = [key.replace('~1', '/').replace('~0', '~') for key in pointer[1:].split('/')]
        parent = config
        for key in keys[:-1]:
            parent = parent.get(key) if isinstance(parent, dict) else None
        if not isinstance(parent, dict) or keys[-1] not in parent:
            raise ValueError(f'{project.id}: model.remove path does not name an existing object key: {pointer}')
        del parent[keys[-1]]
    meshes = config.get('meshes')
    if not isinstance(meshes, dict) or not meshes:
        raise ValueError(f'{project.id}: resolved CHM configuration requires a nonempty meshes object '
                         f'(base: {base}, overrides: {override})')
    for key, value in meshes.items():
        declared_in = origins.get(('meshes', key), base)
        field = f'meshes.{key}'
        if not isinstance(value, str) or not value or '\0' in value:
            raise ValueError(f'{project.id}: {field} in {declared_in} must be a nonempty path')
        source = (declared_in.parent / Path(value).expanduser()).resolve()
        detail = f'{project.id}: {field} from {declared_in} resolves to {source}'
        if not source.is_file():
            raise FileNotFoundError(f'{detail}: mesh input missing')
        if source.is_relative_to(project.work):
            raise ValueError(f'{detail}: mesh inputs must be outside work/')
        for count in re.findall(r'\.np(\d+)', source.name):
            if int(count) != project.model['job']['ranks']:
                raise ValueError(f'{detail}: mesh partition ranks ({count}) do not match '
                                 f'model.job.ranks ({project.model["job"]["ranks"]})')
        meshes[key] = str(source)
    for section in ('option', 'output', 'forcing', 'checkpoint'):
        if section in config and not isinstance(config[section], dict):
            raise ValueError(f'{project.id}: resolved CHM {section} must be an object')
    if 'ugrid' in config.get('output', {}) and not isinstance(config['output']['ugrid'], dict):
        raise ValueError(f'{project.id}: resolved CHM output.ugrid must be an object')
    return config
