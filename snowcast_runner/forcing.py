"""Project archive links, incremental metadata updates and fixed run snapshots."""
from pathlib import Path

from .met import read_index, update_index
from .cog_store import atomic_json


def met_directory(project):
    folder = project.work / 'met'
    if folder.is_symlink():
        raise ValueError(f'Project met directory cannot be a symlink: {folder}')
    folder.mkdir(exist_ok=True)
    return folder


def update_forcing(project):
    archive = project.forcing.get('archive')
    if archive is None:
        raise ValueError('met-update requires forcing.archive; index-only forcing is externally maintained')
    if not archive.is_dir():
        raise FileNotFoundError(f'Forcing archive directory missing: {archive}')
    link = met_directory(project) / 'archive'
    if link.is_symlink() and link.resolve() == archive:
        pass
    elif link.exists() or link.is_symlink():
        raise ValueError(f'Forcing archive link already exists with a different target: {link}')
    else:
        link.symlink_to(archive, target_is_directory=True)
    index = project.forcing['index']
    if project.forcing['managed_index'] and index.is_symlink():
        raise ValueError(f'Managed forcing metadata cannot be a symlink: {index}')
    return update_index(archive, index, start_date=project.model.get('start_date'))


def forcing_index(project):
    if project.forcing.get('archive') is not None:
        update_forcing(project)
    source = project.forcing['index']
    start_date = project.model.get('start_date')
    records = read_index(source, start_date=start_date)
    if not records:
        period = f' on or after {start_date}' if start_date else ''
        raise ValueError(f'No forcing available{period} for {project.id}')
    for row in records:
        if not Path(row['file_name']).is_file():
            raise FileNotFoundError(f'Forcing input missing: {row["file_name"]}')
    # A later archive/index update cannot change an already submitted job's list.
    target = met_directory(project) / 'index.json'
    if target.is_symlink():
        raise ValueError(f'Forcing snapshot cannot be a symlink: {target}')
    atomic_json(target, records)
    return target, max(row['end_time'] for row in records)
