"""Publish COGs and catalogue, then refresh the original-TIFF download index."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import tempfile
import time
import uuid


def _run_with_retry(*commands):
    """Retry SSH/rsync failures using v2's ten attempts and 30s backoff.

    Keep a snapshot's transfer and rename together: if SSH drops after the
    rename succeeds, the next attempt must recreate the temporary remote file.
    """
    delay = 30
    for attempt in range(1, 11):
        try:
            for command in commands:
                subprocess.run(command, check=True)
            return
        except subprocess.CalledProcessError as error:
            if attempt == 10:
                print(f'V3 upload failed after {attempt} attempts: {error}', file=sys.stderr, flush=True)
                raise
            print(f'V3 upload attempt {attempt}/10 failed: {error}. Retrying in {delay}s.',
                  file=sys.stderr, flush=True)
            time.sleep(delay)
            delay *= 2


def _validate_destination(host, directory):
    if not re.fullmatch(r"(?:[A-Za-z0-9_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9_.-]*", host):
        raise ValueError("Use an SSH host or user@host")
    if not directory.startswith('/') or '\n' in directory:
        raise ValueError("Remote data directory must be an absolute path")


def _build_download_index(output):
    script = Path(__file__).resolve().parents[1] / 'scripts/index_tiff_downloads.py'
    subprocess.run([sys.executable, str(script), '--output', str(output)], check=True)


def upload_download_index(host: str, directory: str):
    """Refresh from the public archive and atomically publish to the UI directory."""
    _validate_destination(host, directory)
    with tempfile.TemporaryDirectory(prefix='snowcast-download-index-') as temporary:
        snapshot = Path(temporary) / 'download-index.json'
        # No stale fallback: a failed/empty listing must leave the live index alone.
        _build_download_index(snapshot)
        remote_temp = f'{directory}/.download-index-{uuid.uuid4().hex}.json'
        _run_with_retry(['ssh', host, f'mkdir -p -- {shlex.quote(directory)}'])
        _run_with_retry(
            ['rsync', '-t', '--protect-args', str(snapshot), f'{host}:{remote_temp}'],
            ['ssh', host, f'mv -- {shlex.quote(remote_temp)} {shlex.quote(directory + "/download-index.json")}'],
        )
    print(f'Published TIFF download index → {host}:{directory}/download-index.json')


def upload(data: Path, host: str, directory: str, download_index_directory=None):
    _validate_destination(host, directory)
    index_directory = download_index_directory or str(PurePosixPath(directory).parent)
    _validate_destination(host, index_directory)
    data = Path(data).resolve()
    # Read one snapshot; do not re-read a catalogue that may change mid-upload.
    content = (data / 'catalog.json').read_bytes()
    catalogue = json.loads(content)
    paths = [a['path'] for v in catalogue['variables'] for a in v['assets']]
    for path in paths:
        if not path.startswith('cogs/') or '\n' in path or not (data / path).resolve().is_relative_to(data) or not (data / path).is_file():
            raise ValueError(f"Invalid or missing asset: {path}")
    _run_with_retry(['ssh', host, f'mkdir -p -- {shlex.quote(directory)}'])
    with tempfile.TemporaryDirectory(prefix='snowcast-upload-') as temporary:
        file_list = Path(temporary) / 'files.txt'
        file_list.write_text('\n'.join(paths) + '\n')
        _run_with_retry(['rsync', '-rt', '--protect-args', f'--files-from={file_list}', f'{data}/', f'{host}:{directory}/'])
        snapshot = Path(temporary) / 'catalog.json'
        snapshot.write_bytes(content)
        remote_temp = f'{directory}/.catalog-{uuid.uuid4().hex}.json'
        _run_with_retry(
            ['rsync', '-t', '--protect-args', str(snapshot), f'{host}:{remote_temp}'],
            ['ssh', host, f'mv -- {shlex.quote(remote_temp)} {shlex.quote(directory + "/catalog.json")}'],
        )

    # The normal pipeline uploads original TIFFs before calling us. Read the
    # public listing after publication rather than shipping a UI-build snapshot.
    try:
        upload_download_index(host, index_directory)
    except Exception as error:
        print(f'WARNING: COG catalogue published, but TIFF download index refresh failed: {error}. '
              'The previous download index was retained; retry with --downloads-only.', file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path)
    parser.add_argument('--host', required=True)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--download-index-directory', help='UI directory; defaults to the parent of --directory')
    parser.add_argument('--downloads-only', action='store_true', help='Refresh/upload only the download index; no COG transfer or UI rebuild')
    args = parser.parse_args(argv)
    if args.downloads_only:
        upload_download_index(args.host, args.download_index_directory or str(PurePosixPath(args.directory).parent))
    else:
        if args.data is None:
            parser.error('--data is required unless --downloads-only is used')
        upload(args.data, args.host, args.directory, args.download_index_directory)


if __name__ == '__main__':
    main()
