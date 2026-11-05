"""Copy referenced COGs first, then atomically replace the remote catalogue."""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import uuid


def upload(data: Path, host: str, directory: str):
    if not re.fullmatch(r"(?:[A-Za-z0-9_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9_.-]*", host):
        raise ValueError("Use an SSH host or user@host")
    if not directory.startswith('/') or '\n' in directory:
        raise ValueError("Remote data directory must be an absolute path")
    data = Path(data).resolve()
    # Read one snapshot; do not re-read a catalogue that may change mid-upload.
    content = (data / 'catalog.json').read_bytes()
    catalogue = json.loads(content)
    paths = [a['path'] for v in catalogue['variables'] for a in v['assets']]
    for path in paths:
        if not path.startswith('cogs/') or '\n' in path or not (data / path).resolve().is_relative_to(data) or not (data / path).is_file():
            raise ValueError(f"Invalid or missing asset: {path}")
    subprocess.run(['ssh', host, f'mkdir -p -- {shlex.quote(directory)}'], check=True)
    with tempfile.TemporaryDirectory(prefix='snowcast-upload-') as temporary:
        file_list = Path(temporary) / 'files.txt'
        file_list.write_text('\n'.join(paths) + '\n')
        subprocess.run(['rsync', '-rt', '--protect-args', f'--files-from={file_list}', f'{data}/', f'{host}:{directory}/'], check=True)
        snapshot = Path(temporary) / 'catalog.json'
        snapshot.write_bytes(content)
        remote_temp = f'{directory}/.catalog-{uuid.uuid4().hex}.json'
        subprocess.run(['rsync', '-t', '--protect-args', str(snapshot), f'{host}:{remote_temp}'], check=True)
        subprocess.run(['ssh', host, f'mv -- {shlex.quote(remote_temp)} {shlex.quote(directory + "/catalog.json")}'], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--directory', required=True)
    args = parser.parse_args()
    upload(args.data, args.host, args.directory)
