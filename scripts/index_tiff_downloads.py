"""Index the public original-TIFF directory without downloading raster files."""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request, urlopen

SOURCE = 'https://hpfx.collab.science.gc.ca/~chm003/tiff/'
NAME = re.compile(r'(swe|snowdepthavg|t)-(0\.001|0\.01)x\2_(\d{8}T\d{6})\.tiff?')


class Directory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.files = {}
        self.cells = None
        self.cell = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.cells, self.links = [], []
        elif tag == 'td' and self.cells is not None:
            self.cell = []
        elif tag == 'a' and self.cells is not None:
            href = dict(attrs).get('href', '')
            url = urlsplit(urljoin(SOURCE, href))
            base = urlsplit(SOURCE)
            name = unquote(url.path.removeprefix(base.path))
            if (url.scheme, url.netloc) == (base.scheme, base.netloc) and not url.query and not url.fragment and NAME.fullmatch(name):
                self.links.append(name)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            self.cells.append(''.join(self.cell).strip())
            self.cell = None
        elif tag == 'tr' and self.cells is not None:
            size = self.cells[3] if len(self.cells) > 3 else ''
            size = size if re.fullmatch(r'\d+(?:\.\d+)?[KMGT]?', size) else None
            for name in self.links:
                try:
                    datetime.strptime(NAME.fullmatch(name)[3], '%Y%m%dT%H%M%S')
                except ValueError:
                    continue
                self.files[name] = {'name': name, 'size': size}
            self.cells, self.cell = None, None


def make_index(html):
    directory = Directory()
    directory.feed(html)
    if not directory.files:
        raise ValueError('The directory contained no recognized TIFF files; keeping the previous index.')
    return {
        'version': 1, 'source': SOURCE,
        'indexed_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
        'files': sorted(directory.files.values(), key=lambda f: f['name']),
    }


def write_index(index, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement lets the host serve this index during a scheduled refresh.
    with tempfile.NamedTemporaryFile(mode='w', dir=output.parent, delete=False) as temporary:
        path = Path(temporary.name)
        json.dump(index, temporary, separators=(',', ':'))
        temporary.write('\n')
    try:
        path.chmod(0o644)
        path.replace(output)
    finally:
        path.unlink(missing_ok=True)


def refresh(output, listing=None, allow_stale=False):
    try:
        if listing:
            html = Path(listing).read_text()
        else:
            request = Request(SOURCE, headers={'User-Agent': 'SnowCast-download-index/1.0', 'Cache-Control': 'no-cache'})
            with urlopen(request, timeout=25) as response:
                content = response.read(5_000_001)
                if len(content) > 5_000_000:
                    raise ValueError('Directory listing exceeds 5 MB')
                html = content.decode('utf-8')
        index = make_index(html)
        write_index(index, output)
        print(f"Indexed {len(index['files'])} original TIFFs → {output}")
    except Exception as error:
        if allow_stale and Path(output).is_file():
            previous = json.loads(Path(output).read_text())
            if previous.get('version') == 1 and previous.get('source') == SOURCE and previous.get('files'):
                print(f"WARNING: Could not refresh TIFF index: {error}. Using snapshot from {previous['indexed_at']}.", file=sys.stderr)
                return
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'webui/public/download-index.json')
    parser.add_argument('--listing', type=Path, help='Read a saved directory listing instead of fetching it')
    parser.add_argument('--allow-stale', action='store_true', help='Keep an existing index if refreshing fails')
    args = parser.parse_args()
    refresh(args.output, args.listing, args.allow_stale)
