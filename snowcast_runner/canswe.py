"""Prepare a pinned CanSWE release for the static SnowCast station overlay.

Requires numpy and netCDF4. The browser never downloads/decodes the NetCDF.
"""
from collections import defaultdict
from datetime import date
import hashlib
import gzip
import json
import math
from pathlib import Path
import re

import numpy as np

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


def distance_to_bounds(bounds, lon, lat):
    """Spherical km to a geographic rectangle, including its curved parallels.

    Keep the calculation in sync with webui/src/lib/canswe.ts.
    """
    west, south, east, north = bounds
    if west <= lon <= east:
        return 6371 * math.radians(max(south - lat, lat - north, 0))
    phi, low, high = map(math.radians, (lat, south, north))
    distances = []
    for edge in (west, east):
        delta = math.radians(lon - edge)
        nearest = max(low, min(high, math.atan2(math.sin(phi), math.cos(phi) * math.cos(delta))))
        for target in (low, high, nearest):
            a = math.sin((target - phi) / 2) ** 2 + math.cos(phi) * math.cos(target) * math.sin(delta / 2) ** 2
            distances.append(2 * 6371 * math.asin(math.sqrt(max(0, min(1, a)))))
    return min(distances)


def nearby_distance(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('nearby-km must be a finite nonnegative distance')
    return value


def prepare(source, output, *, domains, entry):
    from netCDF4 import Dataset, num2date

    from .observation_data import verify_source
    verify_source(source, entry)
    nearby_km = nearby_distance(entry['selection']['nearby_km'])
    boxes = [geographic_bounds(d['bounds'], d['id']) for d in domains]
    bounds = [min(b[0] for b in boxes), min(b[1] for b in boxes),
              max(b[2] for b in boxes), max(b[3] for b in boxes)]
    stations = []
    with Dataset(source) as data:
        if data['snd'].units != 'm' or data['snw'].units != 'kg m**-2':
            raise ValueError('Unexpected CanSWE units')
        days = num2date(data['time'][:], data['time'].units, data['time'].calendar)
        dates = [f'{d.year:04d}-{d.month:02d}-{d.day:02d}' for d in days]
        for i, raw_id in enumerate(data['station_id'][:]):
            lon, lat = number(data['lon'][i]), number(data['lat'][i])
            if lon is None or lat is None or not any(distance_to_bounds(b, lon, lat) <= nearby_km for b in boxes):
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
            filename = f'{station_id}-{hashlib.sha256(encoded).hexdigest()[:12]}.json.gz'
            station['href'] = 'stations/' + filename
            target = output / station['href']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(gzip.compress(encoded, compresslevel=9, mtime=0))
            stations.append(station)
        index = {'version': 1, 'dataset': {'name': entry['label'], 'version': entry['release'],
                 **entry['metadata']}, 'bounds': bounds, 'nearby_km': nearby_km, 'minimum_years': MIN_YEARS,
                 'summary': 'All available years; calendar half-month bins; one median per snow year, then 25th/50th/75th percentiles. At least 10 years per range. Sparse bins show individual year medians. No interpolation. Excludes CanSWE QC flags and agency A/C/E/G/M/Y flags.',
                 'stations': sorted(stations, key=lambda s: (s['name'].casefold(), s['id']))}
        if domains is not None:
            index['domains'] = domains
        write_json(output / 'index.json', index)
    print(f'Prepared {len(stations)} CanSWE stations in {output}')
    return index
