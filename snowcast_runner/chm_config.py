"""Resolve authored CHM configurations before creating any run files."""
from pathlib import Path
import re

import json5

from .project import merge, MODEL_RESERVED_NAMES


def _read(source, project_id, kind='CHM configuration'):
    try:
        value = json5.loads(source.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f'{project_id}: cannot read {kind} {source}: {error}') from error
    if not isinstance(value, dict):
        raise ValueError(f'{project_id}: {kind} must be an object: {source}')
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


def model_inputs(project, config):
    """Plan input links without writing state or reading the large mesh files.

    CHM resolves partition entries against its run cwd, not the partition's
    location. Link each relative entry's top-level file/directory from beside
    the source partition, preserving its layout with one link per directory.
    """
    links = {}

    def add(name, source):
        if name in MODEL_RESERVED_NAMES:
            raise ValueError(f'{project.id}: reserved model input name: {name} ({source})')
        if name in links and links[name] != source:
            raise ValueError(f'{project.id}: model input name collision: {name}: {links[name]} and {source}')
        links[name] = source

    for name, source in project.model['assets'].items():
        add(name, source)
    for value in config['meshes'].values():
        source = Path(value)
        add(source.name, source)
        if source.suffix != '.partition':
            continue
        partition = _read(source, project.id, 'CHM partition')
        count = partition.get('ranks')
        if not re.fullmatch(r'[1-9][0-9]*', str(count)):
            raise ValueError(f'{project.id}: partition {source}: ranks must be a positive integer')
        ranks = int(count)
        if ranks != project.model['job']['ranks']:
            raise ValueError(f'{project.id}: partition {source}: ranks ({ranks}) do not match '
                             f'model.job.ranks ({project.model["job"]["ranks"]})')
        for field in ('meshes', 'parameters'):
            entries = partition.get(field, [])
            if not isinstance(entries, list) or (len(entries) != ranks and (field == 'meshes' or entries)):
                raise ValueError(f'{project.id}: partition {source}: {field} must list one file per rank')
            for entry in entries:
                detail = f'{project.id}: partition {source}, {field} entry {entry!r}'
                if not isinstance(entry, str) or not entry or '\0' in entry:
                    raise ValueError(f'{detail}: expected a nonempty file path')
                relative = Path(entry)
                if not relative.is_absolute() and '..' in relative.parts:
                    raise ValueError(f'{detail}: relative paths must stay below the partition directory; '
                                     'use an absolute path for external inputs')
                dependency = (source.parent / relative).resolve()
                if not dependency.is_file():
                    raise FileNotFoundError(f'{detail}: partition input missing: {dependency}')
                if dependency.is_relative_to(project.work):
                    raise ValueError(f'{detail}: partition inputs must be outside work/')
                if not relative.is_absolute():
                    name = relative.parts[0]
                    add(name, (source.parent / name).resolve())
    cwd = project.work / 'chm'
    # Check the whole plan before creating links, including conflicts with
    # user-supplied assets and links left by a different mesh configuration.
    for name, source in links.items():
        target = cwd / name
        if target.is_symlink() and target.resolve() == source:
            continue
        if target.exists() or target.is_symlink():
            raise ValueError(f'{project.id}: model input destination already exists: {target} '
                             f'(expected link to {source})')
    return links
