"""Small stdlib helper for local and SSH archive destinations."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile


def safe_path(root, relative=''):
    root = Path(root).absolute()
    target = root / relative
    if (target != root and root not in target.parents) or '..' in Path(relative).parts:
        raise ValueError('Invalid archive path')
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError('Archive paths cannot contain symlinks')
    return target


def atomic_file(target, source):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.archive-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            if hasattr(source, 'read'):
                import shutil
                shutil.copyfileobj(source, out)
            else:
                out.write(source)
            out.flush(); os.fchmod(out.fileno(), 0o644); os.fsync(out.fileno())
        os.replace(name, target)
    finally:
        try:
            Path(name).unlink()
        except FileNotFoundError:
            pass


@contextmanager
def locked(root):
    root = safe_path(root)
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o755)
    with safe_path(root, '.archive.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield root


def claim(root, project):
    with locked(root) as root:
        owner = safe_path(root, '.snowcast-archive-owner.json')
        identity = {'version': 1, 'project': project}
        if owner.exists() and json.loads(owner.read_text()) != identity:
            raise ValueError('Archive destination belongs to another project; choose a separate directory')
        atomic_file(owner, json.dumps(identity).encode())
        for name in ('tiff', 'asc'):
            directory = safe_path(root, name)
            directory.mkdir(exist_ok=True)
            directory.chmod(0o755)


def commit(root, content):
    index = json.loads(content)
    with locked(root) as root:
        for source in index['sources']:
            for entry in source['files']:
                target = safe_path(root, entry['path'])
                if not target.is_file() or target.stat().st_size != entry['bytes']:
                    raise ValueError(f'Incomplete archive transfer: {entry["path"]}')
        atomic_file(safe_path(root, 'archive-index.json'), content)


if __name__ == '__main__':
    action, root, project = sys.argv[1:]
    if action == 'claim':
        claim(root, project)
    elif action == 'commit':
        commit(root, sys.stdin.buffer.read())
    elif action == 'downloads':
        content = sys.stdin.buffer.read()
        index = json.loads(content)
        if index['project']['id'] != project:
            raise ValueError('Download index identity mismatch')
        with locked(root) as root:
            atomic_file(safe_path(root, 'downloads.json'), content)
    else:
        raise ValueError('Unknown archive action')
