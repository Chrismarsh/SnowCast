"""Validate exports and normalize them to a persistent, per-domain raster grid."""
from datetime import datetime
from contextlib import ExitStack
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import Affine, from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import calculate_default_transform

from postprocess.cog_store import atomic_json
from .jobs import execute, JobFailed

TIFF = re.compile(r'(?P<variable>swe|snowdepthavg|t)-[^_]+_(?P<time>\d{8}T\d{6})\.tiff?$')


def signature(src):
    return {'crs': src.crs.to_string(), 'shape': [src.height, src.width], 'transform': list(src.transform)[:6]}


def aligned(a, b):
    tolerance = max(abs(b['transform'][0]), abs(b['transform'][4])) * 1e-6
    return a['crs'] == b['crs'] and a['shape'] == b['shape'] and all(abs(x-y) <= tolerance for x, y in zip(a['transform'], b['transform']))


def target_grid(src, settings):
    crs = CRS.from_user_input(settings['crs'])
    dx, dy = settings['resolution']
    if settings['bounds']:
        west, south, east, north = settings['bounds']
        width, height = (east-west) / dx, (north-south) / dy
        if not all(round(n) >= 1 and math.isclose(n, round(n), abs_tol=1e-6) for n in (width, height)):
            raise ValueError('Grid bounds must span an integer number of cells')
        width, height = round(width), round(height)
        transform = from_origin(west, north, dx, dy)
    elif src.crs == crs and src.transform.b == src.transform.d == 0 and math.isclose(src.transform.a, dx, rel_tol=1e-3) and math.isclose(-src.transform.e, dy, rel_tol=1e-3):
        # Keep the live western grid's slightly non-nominal spacing exactly.
        transform, width, height = src.transform, src.width, src.height
    else:
        transform, width, height = calculate_default_transform(src.crs, crs, src.width, src.height, *src.bounds, resolution=(dx, dy))
    return {'crs': crs.to_string(), 'shape': [height, width], 'transform': list(transform)[:6]}


def write_raster(src, destination, grid, resampling, driver='GTiff'):
    height, width = grid['shape']
    dtype = src.dtypes[0] if src.dtypes[0] in ('float32', 'float64') else 'float64'
    options = {'driver': driver, 'height': height, 'width': width, 'count': 1, 'dtype': dtype,
               'crs': grid['crs'], 'transform': Affine(*grid['transform']), 'nodata': -9999.0 if driver == 'AAIGrid' else float('nan')}
    if driver == 'GTiff':
        options.update(tiled=True, blockxsize=512, blockysize=512, compress='DEFLATE', BIGTIFF='IF_SAFER')
    with ExitStack() as stack:
        stack.enter_context(rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True))
        virtual = src
        if not aligned(signature(src), grid):
            # GDAL's warper can ignore an external mask when source nodata is
            # also set. Combine both into NaNs before any spatial interpolation.
            temporary = stack.enter_context(tempfile.TemporaryDirectory(prefix='warp-', dir=destination.parent))
            cleaned = Path(temporary) / 'source.tif'
            profile = dict(driver='GTiff', count=1, width=src.width, height=src.height,
                           crs=src.crs, transform=src.transform, dtype=dtype, nodata=float('nan'),
                           tiled=True, blockxsize=512, blockysize=512, compress='DEFLATE', BIGTIFF='IF_SAFER')
            with rasterio.open(cleaned, 'w', **profile) as dst:
                for _, window in dst.block_windows(1):
                    values = src.read(1, window=window, masked=True)
                    mask = np.ma.getmaskarray(values) | ~np.isfinite(values.data)
                    if src.nodata is not None:
                        mask |= values.data == src.nodata
                    data = values.data.astype(dtype)
                    data[mask] = float('nan')
                    dst.write(data, 1, window=window)
            clean_src = stack.enter_context(rasterio.open(cleaned))
            virtual = stack.enter_context(WarpedVRT(clean_src, crs=grid['crs'], transform=options['transform'], width=width,
                                                   height=height, dtype=dtype, nodata=options['nodata'],
                                                   resampling=Resampling[resampling]))
        with rasterio.open(destination, 'w', **options) as dst:
            # Keep physical-value metadata; ASCII has no portable scale/offset,
            # so bake those values into that export instead.
            if driver == 'GTiff':
                dst.scales, dst.offsets = src.scales, src.offsets
            for _, window in dst.block_windows(1):
                values = virtual.read(1, window=window, masked=True)
                mask = np.ma.getmaskarray(values) | ~np.isfinite(values.data)
                if virtual.nodata is not None:
                    mask |= values.data == virtual.nodata
                data = values.data.astype(dtype)
                if driver == 'AAIGrid':
                    data = data * src.scales[0] + src.offsets[0]
                data[mask] = options['nodata']
                dst.write(data, 1, window=window)
                if driver == 'GTiff':
                    dst.write_mask((~mask).astype('uint8') * 255, window=window)


def dataset_files(path):
    return [p for p in path.parent.glob(path.name + '*') if p == path or p.name in
            {path.name + suffix for suffix in ('.msk', '.aux.xml', '.ovr', '.msk.aux.xml', '.ovr.aux.xml')}]


def accept_exports(domain, source, expected_times=None):
    pp = domain.postprocess
    found = {}
    for file in sorted(Path(source).glob('*.tif*')):
        match = TIFF.fullmatch(file.name)
        if not match or match['variable'] not in pp['variables']:
            continue
        datetime.strptime(match['time'], '%Y%m%dT%H%M%S')
        key = match['variable'], match['time']
        if key in found:
            raise ValueError(f'Duplicate variable/time export: {key}')
        found[key] = file
    times = sorted({time for _, time in found})
    if not times or (expected_times is not None and set(times) != set(expected_times)):
        raise ValueError('Exporter did not produce the requested timestamps')
    if set(found) != {(v, t) for v in pp['variables'] for t in times}:
        raise ValueError('Exporter did not produce every requested variable for each timestamp')
    folder = domain.work / 'postprocess'
    folder.mkdir(exist_ok=True)
    state_path = folder / 'grid.json'
    saved = json.loads(state_path.read_text()) if state_path.exists() else None
    if saved and saved['settings'] != pp['grid']:
        raise ValueError('Output grid settings changed; use a new workspace and rebuild its history')
    grid = saved
    with tempfile.TemporaryDirectory(prefix='validated-', dir=folder) as temporary:
        staging = Path(temporary)
        tiffs, ascii_dir = staging / 'tiff', staging / 'ascii'
        tiffs.mkdir(); ascii_dir.mkdir()
        for (variable, stamp), file in found.items():
            with rasterio.open(file) as src:
                if src.count != 1 or src.crs is None or src.dtypes[0].startswith('complex'):
                    raise ValueError(f'Expected a single numeric georeferenced raster: {file}')
                source_grid = signature(src)
                if grid is None:
                    grid = {'version': 1, 'settings': pp['grid'], 'source': source_grid,
                            'target': target_grid(src, pp['grid'])}
                if not aligned(source_grid, grid['source']):
                    raise ValueError(f'Source grid changed: {file}; rebuild on a consistent grid')
                dx, dy = pp['grid']['resolution']
                filename = f'{variable}-{dx:g}x{dy:g}_{stamp}.tiff'
                write_raster(src, tiffs / filename, grid['target'], pp['grid']['resampling'])
                if pp['ascii']['enabled'] and variable in pp['ascii']['variables'] and stamp == times[-1]:
                    ascii_settings = {'crs': 'EPSG:4326', 'resolution': [pp['ascii']['resolution']] * 2, 'bounds': None}
                    write_raster(src, ascii_dir / f'{variable}_{stamp.replace("T", "")}.asc',
                                 target_grid(src, ascii_settings), 'nearest', 'AAIGrid')
        # Validate the complete batch before touching current outputs. Grid state
        # is permanent once a batch is accepted; a later failure can be retried.
        atomic_json(state_path, grid)
        for name, pattern in (('tiff', '*.tiff'), ('ascii', '*.asc')):
            current, archive = folder / name, folder / f'archive_{name}'
            current.mkdir(exist_ok=True); archive.mkdir(exist_ok=True)
            for old in current.glob(pattern):
                for member in dataset_files(old):
                    member.replace(archive / member.name)
                if name == 'ascii':
                    projection = old.with_suffix('.prj')
                    if projection.exists():
                        projection.replace(archive / projection.name)
            for new in (staging / name).iterdir():
                new.replace(current / new.name)
    return {'times': times, 'variables': pp['variables'], 'grid': grid['target']}


def postprocess(domain):
    import xarray as xr
    pp = domain.postprocess
    source = domain.work / 'chm' / 'output' / domain.model['output_file']
    with xr.open_dataset(source) as data:
        if 'time' not in data or not data.time.size:
            raise ValueError(f'Model output has no time coordinate: {source}')
        missing = set(pp['variables']) - set(data.data_vars)
        if missing:
            raise ValueError(f'Model output missing variables: {sorted(missing)}')
        offsets = list(range(max(0, data.time.size - pp['recent_steps']), data.time.size))
        stamps = [str(data.time[i].dt.strftime('%Y%m%dT%H%M%S').item()) for i in offsets]
    folder = domain.work / 'postprocess'
    folder.mkdir(exist_ok=True)
    # A stable staging path lets a scheduler job finish after its launcher exits.
    # Pending PBS jobs are recovered before this directory can be reset.
    raw = folder / 'raw'
    if raw.exists():
        shutil.rmtree(raw)
    command = [pp['exporter'], str(source), '--dxdy', str(pp['source_resolution']),
               '--method', pp['method'], '--timeoffset', *map(str, offsets),
               '--tiff-output', str(raw), '--overwrite', '--variables', *pp['variables']]
    if pp.get('mesh'):
        command.extend(['--mesh', str(pp['mesh'])])
    code, log = execute(command, work=domain.work, cwd=folder, job=pp['job'], label=f'{domain.id}-grid')
    if code:
        raise JobFailed(f'{domain.id}: regridding exit {code}; see {log}')
    return accept_exports(domain, raw, stamps)
