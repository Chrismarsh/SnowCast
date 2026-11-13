"""Locked catalogue publication and delayed cleanup of generated COGs.

Standard library only: the uploader also executes this module on the web host.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import time

GRACE_HOURS = 48
MANAGED = re.compile(r"cogs/(swe|snowdepthavg|t)/\d{8}T\d{6}-[0-9a-f]{20}(?:-[A-Za-z0-9_-]+)?\.tif$")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".catalog-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def store_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def referenced_paths(catalogue):
    if catalogue.get("version") != 1 or not catalogue.get("variables"):
        raise ValueError("Refusing cleanup/publication with an invalid or empty catalogue")
    paths = set()
    for variable in catalogue["variables"]:
        if not variable.get("assets"):
            raise ValueError("Catalogue variable has no assets")
        for asset in variable["assets"]:
            path = asset["path"]
            if not isinstance(path, str):
                raise ValueError(f"Invalid COG path: {path}")
            parts = PurePosixPath(path).parts
            if (path != PurePosixPath(path).as_posix() or len(parts) != 3
                    or parts[0] != "cogs" or parts[1] not in ("swe", "snowdepthavg", "t")
                    or ".." in parts or any(c in path for c in "\n\r\0\\") or not path.endswith(".tif")):
                raise ValueError(f"Invalid COG path: {path}")
            paths.add(path)
    return paths


def verify_assets(root, catalogue):
    root = Path(root)
    for relative in referenced_paths(catalogue):
        path = root / relative
        # Symlink aliases can hide a still-referenced target from cleanup too.
        if any(p.is_symlink() for p in (path, path.parent, root / "cogs")):
            raise ValueError(f"Catalogue asset must not use symlinks: {relative}")
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            raise FileNotFoundError(f"Missing catalogue asset: {relative}")
        asset = next(a for v in catalogue["variables"] for a in v["assets"] if a["path"] == relative)
        if "bytes" in asset and path.stat().st_size != asset["bytes"]:
            raise ValueError(f"Incomplete catalogue asset: {relative}")


def make_assets_public(root, catalogue):
    """Repair new and reused assets before exposing their catalogue, regardless of umask."""
    root = Path(root)
    verify_assets(root, catalogue)
    directories = {root, root / "cogs"}
    for relative in referenced_paths(catalogue):
        path = root / relative
        path.chmod(0o644)
        directories.add(path.parent)
    for directory in directories:
        directory.chmod(0o755)


def cleanup_locked(root, now=None, dry_run=False):
    """Caller holds store_lock. Age starts at first observed loss of references."""
    root = Path(root)
    now = time.time() if now is None else now
    catalogue = json.loads((root / "catalog.json").read_text())
    verify_assets(root, catalogue)
    active = referenced_paths(catalogue)
    protected = set(active)
    pins = root / ".uploads"
    if pins.is_symlink():
        raise ValueError("Upload registry must not be a symlink")
    for pin in pins.glob("*.json"):
        if pin.is_symlink():
            raise ValueError("Upload pin must not be a symlink")
        protected.update(referenced_paths(json.loads(pin.read_text())))
    state_path = root / ".cog-cleanup.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"version": 1, "unreferenced": {}}
    if state.get("version") != 1 or not isinstance(state.get("unreferenced"), dict):
        raise ValueError("Invalid COG cleanup state; no files removed")
    previous = state["unreferenced"]
    unreferenced = {}
    files = {}
    cogs = root / "cogs"
    if cogs.is_symlink():
        raise ValueError("COG directory must not be a symlink")
    for variable in ("swe", "snowdepthavg", "t"):
        directory = cogs / variable
        if directory.is_symlink():
            raise ValueError("COG variable directory must not be a symlink")
        for path in directory.glob("*.tif"):
            relative = path.relative_to(root).as_posix()
            if MANAGED.fullmatch(relative) and not path.is_symlink() and path.is_file():
                files[relative] = path.stat().st_size
    removable = []
    for relative in files:
        if relative in protected:
            continue
        since = previous.get(relative, now)
        if not isinstance(since, (int, float)) or not 0 <= since <= now:
            since = now
        unreferenced[relative] = since
        if now - since >= GRACE_HOURS * 3600:
            removable.append(relative)
    removed_bytes = sum(files[p] for p in removable)
    if not dry_run:
        for relative in removable:
            (root / relative).unlink()
            unreferenced.pop(relative)
        atomic_json(state_path, {"version": 1, "unreferenced": unreferenced})
    active_bytes = sum((root / p).stat().st_size for p in active)
    result = {"active_bytes": active_bytes, "managed_bytes": sum(files.values()) - (0 if dry_run else removed_bytes),
              "removable_bytes": removed_bytes, "removable_files": removable, "dry_run": dry_run}
    print(f"COG storage: {active_bytes / 1e9:.3f} GB active; {result['managed_bytes'] / 1e9:.3f} GB managed; "
          f"{'would remove' if dry_run else 'removed'} {len(removable)} files ({removed_bytes / 1e9:.3f} GB)")
    return result


def remote_action(action, root, token, content=None):
    """Pins protect other uploads; a source's next attempt replaces its stale pin."""
    root = Path(root)
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("Invalid upload token")
    with store_lock(root):
        registry = root / ".uploads"
        if registry.is_symlink():
            raise ValueError("Upload registry must not be a symlink")
        registry.mkdir(exist_ok=True)
        pin = registry / f"{token}.json"
        if action == "pin":
            catalogue = json.loads(content)
            referenced_paths(catalogue)
            atomic_json(pin, catalogue)
        elif action == "unpin":
            pin.unlink(missing_ok=True)
        elif action == "commit":
            catalogue = json.loads(pin.read_text())
            verify_assets(root, catalogue)
            current_path = root / "catalog.json"
            current = json.loads(current_path.read_text()) if current_path.exists() else {}
            stamp = lambda c: datetime.fromisoformat(c["generated_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
            if current and stamp(catalogue) == stamp(current) and catalogue != current:
                raise ValueError("Conflicting catalogues have the same publication timestamp; republish locally")
            if not current or stamp(catalogue) > stamp(current):
                make_assets_public(root, catalogue)
                atomic_json(current_path, catalogue)
            elif catalogue == current:
                make_assets_public(root, catalogue)
                current_path.chmod(0o644)  # Idempotent retry, including old permissions.
            else:
                print("A newer catalogue is already published; retained it")
            pin.unlink()
            try:
                cleanup_locked(root)
            except Exception as error:
                print(f"WARNING: catalogue published; COG cleanup deferred: {error}", file=sys.stderr)
        else:
            raise ValueError("Unknown upload action")


def validate_site_spec(spec):
    """Validate the public-only site contract on both the publisher and host."""
    if (not isinstance(spec, dict) or set(spec) != {'version', 'title', 'domains', 'overview_ranges'}
            or spec['version'] != 1 or not isinstance(spec['title'], str) or not spec['title'].strip()
            or not isinstance(spec['domains'], list)):
        raise ValueError('Invalid site configuration')
    ids = set()
    for entry in spec['domains']:
        if (not isinstance(entry, dict) or set(entry) != {'id', 'name', 'catalogue'}
                or not isinstance(entry['id'], str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', entry['id'])
                or entry['id'] in ids or not isinstance(entry['name'], str) or not entry['name'].strip()
                or entry['catalogue'] != f'data/{entry["id"]}/catalog.json'):
            raise ValueError('Invalid or duplicate site project')
        ids.add(entry['id'])
    ranges = spec['overview_ranges']
    if not isinstance(ranges, dict):
        raise ValueError('Invalid site overview_ranges')
    for variable, span in ranges.items():
        if (variable not in ('swe', 'snowdepthavg', 't') or not isinstance(span, list) or len(span) != 2
                or any(type(n) not in (int, float) or not float('-inf') < n < float('inf') for n in span)
                or span[0] >= span[1]):
            raise ValueError('Invalid site overview_ranges')


def _site_manifest(root, spec):
    domains = []
    for entry in spec['domains']:
        path = root / entry['catalogue']
        if any(p.is_symlink() for p in (root / 'data', path.parent, path)):
            raise ValueError('Site catalogue paths cannot use symlinks')
        available = path.is_file()
        if available:
            catalogue = json.loads(path.read_text())
            if catalogue.get('domain', {}).get('id') != entry['id']:
                raise ValueError(f'Catalogue identity does not match site project {entry["id"]}')
            verify_assets(path.parent, catalogue)
        domains.append({**entry, 'available': available})
    return {**spec, 'domains': domains, 'generated_at': datetime.now(timezone.utc).isoformat()}


def site_action(action, root, spec=None, project_id=None):
    """One host lock protects authoritative selection and independent registration.

    Only configure-site changes selection/order. Publishers must match that
    configuration; an older publisher cannot silently restore a removed project.
    """
    root = Path(root)
    with store_lock(root):
        config = root / '.site-config.json'
        if config.is_symlink() or (root / 'site.json').is_symlink():
            raise ValueError('Site configuration cannot use symlinks')
        if action == 'configure-site':
            validate_site_spec(spec)
            manifest = _site_manifest(root, spec)
            atomic_json(config, spec)
            atomic_json(root / 'site.json', manifest)
        else:
            if not config.is_file():
                raise ValueError('Site is not configured; run snowcast site configure first (with --upload for the host)')
            current = json.loads(config.read_text())
            validate_site_spec(current)
            if spec is not None and spec != current:
                raise ValueError('Site configuration changed; run snowcast site configure before publishing')
            if project_id is not None and project_id not in {d['id'] for d in current['domains']}:
                raise ValueError(f'Project {project_id} is not selected for this site')
            if action == 'register-site':
                if not (root / 'data' / project_id / 'catalog.json').is_file():
                    raise ValueError(f'Project {project_id} has no published catalogue')
                atomic_json(root / 'site.json', _site_manifest(root, current))
            elif action != 'check-site':
                raise ValueError('Unknown site action')
        root.chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["cleanup", "pin", "commit", "unpin", "configure-site", "check-site", "register-site"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("token", nargs="?")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.action == "cleanup":
        with store_lock(args.directory):
            cleanup_locked(args.directory, dry_run=args.dry_run)
    elif args.action.endswith('-site'):
        site_action(args.action, args.directory, json.load(sys.stdin), args.token)
    else:
        remote_action(args.action, args.directory, args.token, sys.stdin.read() if args.action == "pin" else None)


if __name__ == "__main__":
    main()
