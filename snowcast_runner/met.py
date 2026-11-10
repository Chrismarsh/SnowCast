"""Incremental CHM forcing metadata, shared by the project and legacy runners."""
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re

from .cog_store import atomic_json

TIME_FORMAT = '%Y%m%dT%H%M%S'


def start_time(start_date):
    """Use the same inclusive midnight cutoff for metadata and CHM."""
    return datetime.strptime(start_date, '%Y-%m-%d').strftime(TIME_FORMAT) if start_date else None


def daily_file_date(filename):
    """Recognize complete daily names only; other files need their time axis."""
    stem = Path(filename).stem
    if re.fullmatch(r'\d{8}', stem):
        return datetime.strptime(stem, '%Y%m%d').date()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', stem):
        return datetime.strptime(stem, '%Y-%m-%d').date()
    return None


def _records(index):
    records = json.loads(index.read_text())
    if not isinstance(records, list):
        raise ValueError(f'Forcing index must be a list: {index}')
    for row in records:
        if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k]
                                           for k in ('start_time', 'end_time', 'file_name')):
            raise ValueError(f'Invalid forcing metadata record in {index}: {row}')
        start, end = [datetime.strptime(row[k], TIME_FORMAT) for k in ('start_time', 'end_time')]
        if start > end:
            raise ValueError(f'Invalid forcing interval in {index}: {row}')
    return records


def read_index(index, *, start_date=None):
    """Read existing metadata without opening NetCDFs; resolve eligible paths."""
    index = Path(index).resolve()
    cutoff = start_time(start_date)
    selected = []
    for row in _records(index):
        if cutoff is not None and row['end_time'] < cutoff:
            continue
        row['file_name'] = str((index.parent / row['file_name']).resolve())
        selected.append(row)
    return selected


def update_index(archive, index, *, start_date=None):
    """Append unindexed *.nc files, opening only their time coordinates.

    Lock the canonical index path so symlink aliases and both runners share the
    same lock, even when the archive itself is mounted read-only. Existing
    entries are authoritative; neither archive files nor old entries are pruned.
    Daily filenames before start_date are skipped before resolution/stat/open.
    """
    import xarray as xr

    archive, index = Path(archive).resolve(), Path(index).resolve()
    cutoff = start_time(start_date)
    cutoff_day = datetime.strptime(cutoff, TIME_FORMAT).date() if cutoff else None
    if not archive.is_dir():
        raise FileNotFoundError(f'Forcing archive directory missing: {archive}')
    index.parent.mkdir(parents=True, exist_ok=True)
    with index.with_name(f'.{index.name}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        binding = index.with_name(f'.{index.name}.archive.json')
        identity = {'version': 1, 'archive': str(archive)}
        if binding.is_symlink():
            raise ValueError(f'Forcing index archive binding cannot be a symlink: {binding}')
        if binding.exists() and json.loads(binding.read_text()) != identity:
            raise ValueError(f'Forcing index belongs to a different archive; use a separate index: {index}')
        records = _records(index) if index.exists() else []
        known = {os.path.abspath(index.parent / row['file_name']) for row in records}
        active_paths = set()
        for row in records:
            if cutoff is not None and row['end_time'] < cutoff:
                continue
            row['file_name'] = str((index.parent / row['file_name']).resolve())
            known.add(row['file_name'])
            active_paths.add(row['file_name'])
        if any(Path(name).parent != archive for name in active_paths):
            raise ValueError(f'Forcing index contains files from a different archive; use a separate index: {index}')
        added = 0
        skipped = 0
        for candidate in sorted(archive.glob('*.nc')):
            day = daily_file_date(candidate) if cutoff_day else None
            if day is not None and day < cutoff_day:
                skipped += 1
                continue
            if str(candidate) in known:
                continue
            filename = candidate.resolve()
            if str(filename) in known:
                continue
            before = filename.stat()
            with xr.open_dataset(filename) as data:
                if 'time' not in data.coords or data.time.size == 0:
                    raise ValueError(f'Forcing has no time coordinates: {filename}')
                try:
                    start = str(data.time.min().dt.strftime(TIME_FORMAT).item())
                    end = str(data.time.max().dt.strftime(TIME_FORMAT).item())
                    if datetime.strptime(start, TIME_FORMAT) > datetime.strptime(end, TIME_FORMAT):
                        raise ValueError('Reversed time interval')
                except (AttributeError, TypeError, ValueError) as error:
                    raise ValueError(f'Invalid forcing times: {filename}') from error
            after = filename.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError(f'Forcing file changed while reading metadata; retry when complete: {filename}')
            records.append({'start_time': start, 'end_time': end, 'file_name': str(filename)})
            known.add(str(filename))
            added += 1
        active = [row for row in records if cutoff is None or row['end_time'] >= cutoff]
        if not active:
            period = f' on or after {start_date}' if start_date else ''
            raise ValueError(f'No forcing available{period} in {archive}')
        if not binding.exists():
            atomic_json(binding, identity)
        if added:
            records.sort(key=lambda row: (row['start_time'], row['file_name']))
            # Commit only after every new file was read successfully. A bad or
            # partially written file leaves the previous JSON untouched.
            atomic_json(index, records)
        return {'index': str(index), 'added': added, 'files': len(records), 'active_files': len(active),
                'skipped_before_start': skipped, 'start_date': start_date,
                'latest_time': max(row['end_time'] for row in active)}
