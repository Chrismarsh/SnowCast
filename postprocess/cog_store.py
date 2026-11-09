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
            parts = PurePosixPath(path).parts
            if (len(parts) != 3 or parts[0] != "cogs" or parts[1] not in ("swe", "snowdepthavg", "t")
                    or ".." in parts or "\n" in path or "\\" in path or not path.endswith(".tif")):
                raise ValueError(f"Invalid COG path: {path}")
            paths.add(path)
    return paths


def verify_assets(root, catalogue):
    for relative in referenced_paths(catalogue):
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            raise FileNotFoundError(f"Missing catalogue asset: {relative}")
        asset = next(a for v in catalogue["variables"] for a in v["assets"] if a["path"] == relative)
        if "bytes" in asset and path.stat().st_size != asset["bytes"]:
            raise ValueError(f"Incomplete catalogue asset: {relative}")


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
            if not current or stamp(catalogue) >= stamp(current):
                atomic_json(current_path, catalogue)
            else:
                print("A newer catalogue is already published; retained it")
            pin.unlink()
            try:
                cleanup_locked(root)
            except Exception as error:
                print(f"WARNING: catalogue published; COG cleanup deferred: {error}", file=sys.stderr)
        else:
            raise ValueError("Unknown upload action")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["cleanup", "pin", "commit", "unpin"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("token", nargs="?")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.action == "cleanup":
        with store_lock(args.directory):
            cleanup_locked(args.directory, dry_run=args.dry_run)
    else:
        remote_action(args.action, args.directory, args.token, sys.stdin.read() if args.action == "pin" else None)


if __name__ == "__main__":
    main()
