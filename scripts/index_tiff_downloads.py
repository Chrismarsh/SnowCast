"""Index public daily GeoTIFF and AEP ASCII downloads without fetching rasters."""
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
ASCII_SOURCE = 'https://hpfx.collab.science.gc.ca/~chm003/asc/'
NAME = re.compile(r'(swe|snowdepthavg|t)-0\.001x0\.001_(?P<time>\d{8}T\d{6})\.tiff?')
ASCII_NAME = re.compile(r'(swe|snowdepthavg|t)_(?P<time>\d{14})\.asc')


class Directory(HTMLParser):
    def __init__(self, source=SOURCE, pattern=NAME, time_format='%Y%m%dT%H%M%S'):
        super().__init__()
        self.source, self.pattern, self.time_format = source, pattern, time_format
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
            url = urlsplit(urljoin(self.source, href))
            base = urlsplit(self.source)
            name = unquote(url.path.removeprefix(base.path))
            if (url.scheme, url.netloc) == (base.scheme, base.netloc) and not url.query and not url.fragment and self.pattern.fullmatch(name):
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
                    datetime.strptime(self.pattern.fullmatch(name)['time'], self.time_format)
                except ValueError:
                    continue
                self.files[name] = {'name': name, 'size': size}
            self.cells, self.cell = None, None


def make_index(html, ascii_html):
    directory = Directory()
    directory.feed(html)
    ascii_directory = Directory(ASCII_SOURCE, ASCII_NAME, '%Y%m%d%H%M%S')
    ascii_directory.feed(ascii_html)
    if not directory.files:
        raise ValueError('The directory contained no recognized TIFF files; keeping the previous index.')
    if not ascii_directory.files:
        raise ValueError('The directory contained no recognized ASCII files; keeping the previous index.')
    return {
        'version': 1, 'source': SOURCE, 'ascii_source': ASCII_SOURCE,
        'indexed_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
        'files': sorted([*directory.files.values(), *ascii_directory.files.values()], key=lambda f: f['name']),
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


def read_listing(source, listing):
    if listing:
        return Path(listing).read_text()
    request = Request(source, headers={'User-Agent': 'SnowCast-download-index/1.0', 'Cache-Control': 'no-cache'})
    with urlopen(request, timeout=25) as response:
        content = response.read(5_000_001)
        if len(content) > 5_000_000:
            raise ValueError('Directory listing exceeds 5 MB')
        return content.decode('utf-8')


def refresh(output, listing=None, allow_stale=False, ascii_listing=None):
    if bool(listing) != bool(ascii_listing):
        raise ValueError('Provide both --listing and --ascii-listing for an offline refresh')
    try:
        index = make_index(read_listing(SOURCE, listing), read_listing(ASCII_SOURCE, ascii_listing))
        write_index(index, output)
        print(f"Indexed {len(index['files'])} daily GeoTIFF/ASCII files → {output}")
    except Exception as error:
        if allow_stale and Path(output).is_file():
            previous = json.loads(Path(output).read_text())
            if previous.get('version') == 1 and previous.get('source') == SOURCE and previous.get('files'):
                print(f"WARNING: Could not refresh download index: {error}. Using snapshot from {previous['indexed_at']}.", file=sys.stderr)
                return
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'webui/public/download-index.json')
    parser.add_argument('--listing', type=Path, help='Read a saved directory listing instead of fetching it')
    parser.add_argument('--ascii-listing', type=Path, help='Saved ASCII directory listing; use together with --listing')
    parser.add_argument('--allow-stale', action='store_true', help='Keep an existing index if refreshing fails')
    args = parser.parse_args()
    refresh(args.output, args.listing, args.allow_stale, args.ascii_listing)
