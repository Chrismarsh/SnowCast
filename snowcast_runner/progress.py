"""Flushed progress messages, scoped to one CLI invocation."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import sys


_PROJECT = ContextVar('snowcast_progress_project', default=None)


@contextmanager
def reporting(project, *, enabled=True):
    token = _PROJECT.set(project if enabled else None)
    try:
        yield
    finally:
        _PROJECT.reset(token)


def elapsed(seconds):
    return str(timedelta(seconds=int(seconds)))


def progress(message):
    project = _PROJECT.get()
    if project is not None:
        stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        print(f'[{stamp}] {project}: {message}', file=sys.stderr, flush=True)
