"""Publish COGs and catalogue, then refresh the original-TIFF download index."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
import uuid


from .cog_store import referenced_paths, store_lock, verify_assets


def _run_with_retry(*commands, input=None):
    """Retry SSH/rsync failures using v2's ten attempts and 30s backoff.

    Keep a snapshot's transfer and rename together: if SSH drops after the
    rename succeeds, the next attempt must recreate the temporary remote file.
    """
    delay = 30
    for attempt in range(1, 11):
        try:
            for command in commands:
                subprocess.run(command, check=True, **({"input": input} if input is not None else {}))
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
    from .downloads import refresh
    refresh(output)


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
            ['rsync', '-tp', '--chmod=F644', '--protect-args', str(snapshot), f'{host}:{remote_temp}'],
            ['ssh', host, f'mv -- {shlex.quote(remote_temp)} {shlex.quote(directory + "/download-index.json")}'],
        )
    print(f'Published TIFF download index → {host}:{directory}/download-index.json')


def _remote_store(host, directory, action, token):
    # Ship the stdlib-only helper with the command; no repo install on the host.
    source = Path(__file__).with_name('cog_store.py').read_text()
    command = ' '.join(shlex.quote(part) for part in ('python3', '-c', source, action, directory, token))
    return ['ssh', host, command]


def upload(data: Path, host: str, directory: str, download_index_directory=None):
    _validate_destination(host, directory)
    index_directory = download_index_directory or str(PurePosixPath(directory).parent)
    _validate_destination(host, index_directory)
    data = Path(data).resolve()
    # One local publisher/uploader at a time, including retries. A failed process
    # releases the lock automatically. Its next attempt replaces the remote pin.
    with store_lock(data):
        content = (data / 'catalog.json').read_bytes()
        catalogue = json.loads(content)
        verify_assets(data, catalogue)
        paths = sorted(referenced_paths(catalogue))
        token = uuid.uuid5(uuid.NAMESPACE_URL, f'{socket.gethostname()}:{data}').hex
        pin = _remote_store(host, directory, 'pin', token)
        commit = _remote_store(host, directory, 'commit', token)
        committed = False
        try:
            # Protect this snapshot on the host before any asset transfer.
            _run_with_retry(pin, input=content)
            with tempfile.TemporaryDirectory(prefix='snowcast-upload-') as temporary:
                file_list = Path(temporary) / 'files.txt'
                file_list.write_text('\n'.join(paths) + '\n')
                _run_with_retry(['rsync', '-rtp', '--chmod=D755,F644', '--protect-args', f'--files-from={file_list}', f'{data}/', f'{host}:{directory}/'])
            # Re-pin on retries: the commit may have succeeded before SSH dropped.
            _run_with_retry(pin, commit, input=content)
            committed = True
        finally:
            if not committed:
                try:
                    subprocess.run(_remote_store(host, directory, 'unpin', token), check=True)
                except Exception as error:
                    print(f'WARNING: upload pin retained on host; next upload from this source will replace it: {error}', file=sys.stderr)

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
