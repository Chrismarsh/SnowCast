"""Install the bundled CanSWE snapshot into the static assets (stdlib only)."""
import json
from pathlib import Path
import re
import zipfile


def unpack(bundle, output):
    with zipfile.ZipFile(bundle) as archive:
        index = json.loads(archive.read('index.json'))
        if index.get('version') != 1 or not index.get('stations'):
            raise ValueError('Invalid bundled station index')
        names = [s['href'] for s in index['stations']]
        if any(not re.fullmatch(r'stations/[A-Za-z0-9_.-]+\.json\.gz', name) for name in names):
            raise ValueError('Invalid bundled station path')
        for name in [*names, 'index.json']:
            data = archive.read(name)
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or path.read_bytes() != data:
                temporary = path.with_suffix('.tmp')
                temporary.write_bytes(data)
                temporary.replace(path)
    print(f'CanSWE: {len(names)} station histories ready')


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    unpack(root / 'webui/data/canswe-v8.zip', root / 'webui/public/observations/canswe')
