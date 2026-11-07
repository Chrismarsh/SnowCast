"""Verify an actual range GET; Accept-Ranges alone is not sufficient."""
import argparse
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('url', help='Public URL of one COG')
parser.add_argument('--origin', help='Viewer origin, e.g. https://www.snowcast.ca')
args = parser.parse_args()
headers = {'Range': 'bytes=0-1023', 'Accept-Encoding': 'identity'}
if args.origin:
    headers['Origin'] = args.origin
with urlopen(Request(args.url, headers=headers), timeout=30) as response:
    data = response.read(1025)
    if response.status != 206 or not response.headers.get('Content-Range', '').startswith('bytes 0-1023/') or len(data) != 1024:
        raise SystemExit(f'FAIL: expected HTTP 206 and exactly 1024 bytes; got {response.status}, {len(data)} bytes, Content-Range={response.headers.get("Content-Range")}')
    if response.headers.get('Content-Encoding', 'identity') != 'identity':
        raise SystemExit('FAIL: COG response is HTTP-compressed; disable gzip/brotli for TIFFs')
    if args.origin and response.headers.get('Access-Control-Allow-Origin') not in ('*', args.origin):
        raise SystemExit('FAIL: cross-origin access is not allowed for the viewer origin')
    print('PASS: actual byte-range GET returned HTTP 206 with the requested bytes.')
    if args.origin:
        print('PASS: Access-Control-Allow-Origin permits the supplied viewer origin.')
