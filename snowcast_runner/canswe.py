"""Prepare a pinned CanSWE release for the static SnowCast station overlay.

Requires numpy and netCDF4. The browser never downloads/decodes the NetCDF.
"""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import gzip
import json
import math
import os
from pathlib import Path
import re
import tempfile
import zipfile

import numpy as np

DOI = 'https://doi.org/10.5281/zenodo.19075529'
SOURCE_MD5 = 'd7eb41a9cbbce88ff399185402826a44'
DEFAULT_BOUNDS = [-132, 46.4, -109.8, 56]
MIN_YEARS = 10
METHODS = ['Manual snow survey', 'Manual single point', 'Snow pillow / scale',
           'Passive gamma', 'GNSS / GPS', 'Cosmic ray', 'Time domain reflectometry']


def halfmonth(value):
    """24 calendar bins, August first; never interpolate between bins."""
    return ((value.month - 8) % 12) * 2 + (value.day > 15)


def snowyear(value):
    return value.year + (value.month >= 8)


def summaries(rows, column, minimum=MIN_YEARS):
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        # Keep agency flags in downloads, but exclude sampling problems,
        # estimates, distant/uncertain locations/dates from seasonal statistics.
        if row[column] is not None and row[column + 2] not in {'A', 'C', 'E', 'G', 'M', 'Y'} and not row[column + 4]:
            when = date.fromisoformat(row[0])
            grouped[halfmonth(when)][snowyear(when)].append(row[column])
    result = []
    for b in range(24):
        years = grouped[b]
        # One contribution per snow year, regardless of sampling frequency.
        values = [float(np.median(samples)) for samples in years.values()]
        quantiles = np.quantile(values, [0.25, 0.5, 0.75]).tolist() if len(years) >= minimum else [None] * 3
        result.append({'bin': b, 'years': len(years), 'first': min(years, default=None),
                       'last': max(years, default=None), 'q25': quantiles[0],
                       'median': quantiles[1], 'q75': quantiles[2],
                       'samples': [[year, float(np.median(samples))] for year, samples in sorted(years.items())] if len(years) < minimum else []})
    return result


def number(value):
    return None if np.ma.is_masked(value) or not np.isfinite(value) else float(value)


def flag(value):
    if np.ma.is_masked(value):
        return ''
    return bytes(value).decode('ascii').strip('\x00 ')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(content)
    temporary.replace(path)


def geographic_bounds(bounds, where):
    if (not isinstance(bounds, (list, tuple)) or len(bounds) != 4 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in bounds) or
            not (-180 <= bounds[0] < bounds[2] <= 180 and -90 <= bounds[1] < bounds[3] <= 90)):
        raise ValueError(f'{where}: expected geographic bounds [west, south, east, north]')
    return list(bounds)


def contains(bounds, lon, lat):
    return bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]


def site_domains(site):
    """Use actual WGS84 catalogue bounds, not grid bounds in a projected CRS."""
    domains = []
    for project in site.projects:
        catalogue = site.staging / 'data' / project.id / 'catalog.json'
        if not catalogue.is_file():
            raise ValueError(f'{project.id}: no local catalogue at {catalogue}; first run '
                             f'snowcast publish SITE_CONFIG --project {project.id} --no-upload')
        data = json.loads(catalogue.read_text())
        if (not isinstance(data, dict) or data.get('version') != 1 or
                not isinstance(data.get('domain'), dict) or data['domain'].get('id') != project.id):
            raise ValueError(f'{project.id}: invalid or mismatched project catalogue: {catalogue}')
        domains.append({'id': project.id, 'name': project.name,
                        'bounds': geographic_bounds(data.get('bounds'), project.id)})
    return domains


def prepare_site_bundle(site, source, bundle):
    """Regenerate locally; an incomplete selection never replaces the old bundle."""
    domains = site_domains(site)
    source, bundle = Path(source).expanduser().resolve(), Path(bundle).expanduser().resolve()
    if source == bundle:
        raise ValueError('CanSWE source and output bundle must be different files')
    with tempfile.TemporaryDirectory(prefix='snowcast-canswe-') as temporary:
        output = Path(temporary)
        index = prepare(source, output, domains=domains)
        pack(output, bundle)
    for domain in domains:
        count = sum(contains(domain['bounds'], s['lon'], s['lat']) for s in index['stations'])
        print(f'{domain["name"]} ({domain["id"]}): {count} CanSWE stations')
    return index


def pack(output, bundle):
    """One reproducible git artifact; extract for the dev server and builds.

    Individual histories remain gzipped and are decoded after a station click.
    This avoids relying on hosting-specific gzip configuration.
    """
    index = json.loads((output / 'index.json').read_text())
    entries = {}
    for station in index['stations']:
        path = output / station['href']
        raw = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
        station['href'] = station['href'].removesuffix('.gz') + '.gz'
        entries[station['href']] = gzip.compress(raw, compresslevel=9, mtime=0)
    entries['index.json'] = (json.dumps(index, separators=(',', ':'), ensure_ascii=False) + '\n').encode()
    bundle.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=bundle.parent, prefix=f'.{bundle.name}.', suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
                for name, content in sorted(entries.items()):
                    entry = zipfile.ZipInfo(name, date_time=(2026, 3, 17, 0, 0, 0))
                    entry.external_attr = 0o644 << 16
                    archive.writestr(entry, content)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            temporary.replace(bundle)
        finally:
            temporary.unlink(missing_ok=True)
    print(f'Packed {len(index["stations"])} histories → {bundle} ({bundle.stat().st_size:,} bytes)')


def prepare(source, output, bounds=DEFAULT_BOUNDS, *, domains=None):
    from netCDF4 import Dataset, num2date

    boxes = [geographic_bounds(d['bounds'], d['id']) for d in domains] if domains else [geographic_bounds(bounds, 'CanSWE')]
    bounds = [min(b[0] for b in boxes), min(b[1] for b in boxes),
              max(b[2] for b in boxes), max(b[3] for b in boxes)]
    checksum = hashlib.md5()
    with source.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
    digest = checksum.hexdigest()
    if digest != SOURCE_MD5:
        raise ValueError('Input does not match the pinned CanSWE v8 file; review release metadata before updating.')
    stations = []
    with Dataset(source) as data:
        if data['snd'].units != 'm' or data['snw'].units != 'kg m**-2':
            raise ValueError('Unexpected CanSWE units')
        days = num2date(data['time'][:], data['time'].units, data['time'].calendar)
        dates = [f'{d.year:04d}-{d.month:02d}-{d.day:02d}' for d in days]
        for i, raw_id in enumerate(data['station_id'][:]):
            lon, lat = number(data['lon'][i]), number(data['lat'][i])
            if lon is None or lat is None or not any(contains(b, lon, lat) for b in boxes):
                continue
            station_id = str(raw_id)
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', station_id):
                raise ValueError(f'Unsafe station ID: {station_id!r}')
            # Preserve the existing licence guard when expanding the selection.
            if station_id.startswith('HQ') or 'quebec' in str(data['source'][i]).lower():
                raise ValueError('Hydro-Quebec data requires separate licence handling')
            swe, depth = data['snw'][i], data['snd'][i]
            flags = [data[key][i, :, 0] for key in ['data_flag_snw', 'data_flag_snd', 'qc_flag_snw', 'qc_flag_snd']]
            present = ~np.ma.getmaskarray(swe) | ~np.ma.getmaskarray(depth)
            for values in flags:
                present |= ~np.ma.getmaskarray(values) & (np.ma.filled(values, b'') != b'')
            rows = [[dates[j], number(swe[j]), number(depth[j]), *(flag(values[j]) for values in flags)]
                    for j in np.flatnonzero(present)]
            valid = [r for r in rows if r[1] is not None or r[2] is not None]
            if not valid:
                continue
            kind = int(data['type_mes'][i])
            station = {'id': station_id, 'name': str(data['station_name'][i]),
                       'lon': lon, 'lat': lat, 'elevation': number(data['elevation'][i]),
                       'agency': str(data['source'][i]), 'method': METHODS[kind] if 0 <= kind < len(METHODS) else 'Unknown',
                       'automated': kind >= 2, 'first': valid[0][0], 'last': valid[-1][0],
                       'counts': {'swe': sum(r[1] is not None for r in rows), 'depth': sum(r[2] is not None for r in rows)}}
            detail = {'version': 1, 'id': station_id, 'records': rows,
                      'seasonal': {'swe': summaries(rows, 1), 'depth': summaries(rows, 2)}}
            encoded = json.dumps(detail, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
            # Immutable detail URLs; publish index last. Old pages can finish
            # reading the same snapshot during an update.
            filename = f'{station_id}-{hashlib.sha256(encoded).hexdigest()[:12]}.json'
            station['href'] = 'stations/' + filename
            write_json(output / station['href'], detail)
            stations.append(station)
        index = {'version': 1, 'dataset': {'name': 'CanSWE', 'version': 'v8', 'doi': DOI,
                 'through': '2025-07-31', 'citation': 'Vionnet, Mortimer, Brady, Arnal & Brown (2026), CanSWE v8.',
                 'licence': 'Open Government Licence – Canada', 'licence_url': 'https://open.canada.ca/en/open-government-licence-canada',
                 'source_md5': digest}, 'bounds': bounds, 'minimum_years': MIN_YEARS,
                 'summary': 'All available years; calendar half-month bins; one median per snow year, then 25th/50th/75th percentiles. At least 10 years per range. Sparse bins show individual year medians. No interpolation. Excludes CanSWE QC flags and agency A/C/E/G/M/Y flags.',
                 'stations': sorted(stations, key=lambda s: (s['name'].casefold(), s['id']))}
        if not stations:
            raise ValueError('No stations found; existing index left unchanged')
        if domains is not None:
            index['domains'] = domains
        write_json(output / 'index.json', index)
    print(f'Prepared {len(stations)} CanSWE stations in {output}')
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Pinned CanSWE-CanEEN_1928-2025_v8.nc')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bounds', type=float, nargs=4, default=DEFAULT_BOUNDS, metavar=('WEST', 'SOUTH', 'EAST', 'NORTH'))
    parser.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(argv)
    prepare(args.source, args.output, args.bounds)
    pack(args.output, args.bundle)


if __name__ == '__main__':
    main()
