"""Workspace ownership and process locks, independent of the code checkout."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path

from postprocess.cog_store import atomic_json

RUN_LOCK_FD = ContextVar('snowcast_run_lock_fd', default=None)


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def workspace(project, domain):
    project.work_root.mkdir(parents=True, exist_ok=True)
    with (project.work_root / '.owner.lock').open('a') as owner_lock:
        fcntl.flock(owner_lock, fcntl.LOCK_EX)
        owner = project.work_root / 'project-owner.json'
        identity = {'version': 1, 'project': project.id}
        if owner.exists() and json.loads(owner.read_text()) != identity:
            raise ValueError('This work_root already belongs to a different project')
        atomic_json(owner, identity)
        if domain.work.is_symlink():
            raise ValueError('Domain workspace cannot be a symlink')
        domain.work.mkdir(exist_ok=True)
    with (domain.work / '.run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f'{domain.id} is already running') from None
        # The lock file is never unlinked: waiters must all lock the same inode.
        token = RUN_LOCK_FD.set(lock.fileno())
        try:
            yield domain.work
        finally:
            RUN_LOCK_FD.reset(token)


def status(domain, state, **detail):
    atomic_json(domain.work / 'status.json', {'version': 1, 'domain': domain.id,
                                            'state': state, 'updated_at': now(), **detail})
