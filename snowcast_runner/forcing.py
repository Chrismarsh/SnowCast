"""Domain archive links, incremental metadata updates and fixed run snapshots."""
from pathlib import Path

from met.main import read_index, update_index
from postprocess.cog_store import atomic_json


def met_directory(domain):
    folder = domain.work / 'met'
    if folder.is_symlink():
        raise ValueError(f'Domain met directory cannot be a symlink: {folder}')
    folder.mkdir(exist_ok=True)
    return folder


def update_forcing(domain):
    archive = domain.forcing.get('archive')
    if archive is None:
        raise ValueError('met-update requires forcing.archive; index-only forcing is externally maintained')
    if not archive.is_dir():
        raise FileNotFoundError(f'Forcing archive directory missing: {archive}')
    link = met_directory(domain) / 'archive'
    if link.is_symlink() and link.resolve() == archive:
        pass
    elif link.exists() or link.is_symlink():
        raise ValueError(f'Forcing archive link already exists with a different target: {link}')
    else:
        link.symlink_to(archive, target_is_directory=True)
    return update_index(link, domain.forcing['index'])


def forcing_index(domain):
    if domain.forcing.get('archive') is not None:
        update_forcing(domain)
    source = domain.forcing['index']
    records = read_index(source)
    if not records:
        raise ValueError(f'No forcing available for {domain.id}')
    for row in records:
        if not Path(row['file_name']).is_file():
            raise FileNotFoundError(f'Forcing input missing: {row["file_name"]}')
    # A later archive/index update cannot change an already submitted job's list.
    target = met_directory(domain) / 'index.json'
    if target.is_symlink():
        raise ValueError(f'Forcing snapshot cannot be a symlink: {target}')
    atomic_json(target, records)
    return target, max(row['end_time'] for row in records)
