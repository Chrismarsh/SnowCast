"""Workspace ownership and process locks, independent of the code checkout."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path

from .cog_store import atomic_json

RUN_LOCK_FD = ContextVar('snowcast_run_lock_fd', default=None)


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def workspace(project):
    if project.work.is_symlink():
        raise ValueError('Project work directory cannot be a symlink')
    # Explicit input aliases may point elsewhere, but managed execution and
    # product paths must never redirect writes into another project's state.
    managed = ('.owner.lock', '.run.lock', 'project-owner.json', 'status.json',
               'met', 'met/metadata.json', 'met/index.json', 'chm', 'chm/config.json',
               'chm/log', 'chm/output', 'chm/output/checkpoint', 'jobs', 'postprocess',
               'postprocess/raw', 'postprocess/grid.json', 'postprocess/tiff',
               'postprocess/ascii', 'postprocess/archive_tiff', 'postprocess/archive_ascii', 'archive')
    for relative in managed:
        target = project.work / relative
        if target.is_symlink():
            raise ValueError(f'{project.id}: managed project path cannot be a symlink: {target}')
    project.work.mkdir(parents=True, exist_ok=True)
    with (project.work / '.owner.lock').open('a') as owner_lock:
        fcntl.flock(owner_lock, fcntl.LOCK_EX)
        owner = project.work / 'project-owner.json'
        identity = {'version': 2, 'project': project.id}
        if owner.exists() and json.loads(owner.read_text()) != identity:
            raise ValueError('This work directory already belongs to a different project or legacy workspace')
        atomic_json(owner, identity)
    with (project.work / '.run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f'{project.id} is already running') from None
        # The lock file is never unlinked: waiters must all lock the same inode.
        token = RUN_LOCK_FD.set(lock.fileno())
        try:
            yield project.work
        finally:
            RUN_LOCK_FD.reset(token)


def status(project, state, **detail):
    atomic_json(project.work / 'status.json', {'version': 2, 'project': project.id,
                                            'state': state, 'updated_at': now(), **detail})
