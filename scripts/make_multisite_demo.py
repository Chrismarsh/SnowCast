"""Small synthetic domains with different ranges, grids, timestamps and gaps."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_bounds

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from snowcast_runner.publish_cogs import publish
from snowcast_runner.cog_store import atomic_json, site_action


def main():
    output = ROOT / 'webui/public/demo-site'
    definitions = [
        ('western-cordillera', 'Western Cordillera', [-125, 48, -110, 60], [9, 10, 11, 12], 23, 400),
        ('tvc', 'Trail Valley Creek', [-135, 67, -130, 70], [9, 10, 12], 18, 100),
        ('overlap', 'Overlapping research site', [-117, 50, -115, 52], [10, 11, 12], 21, 200),
    ]
    for identity, name, bounds, days, hour, maximum in definitions:
        size = 256
        transform = from_bounds(*bounds, size, size)
        grid = f'{transform.a}x{-transform.e}'
        y, x = np.mgrid[:size, :size] / size
        terrain = (x + y) / 2
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for day in days:
                when = datetime(2026, 11, day, hour, tzinfo=timezone.utc)
                for variable in ['swe', 'snowdepthavg', 't']:
                    values = terrain * maximum * day / 12
                    if variable == 'snowdepthavg':
                        values /= 200
                    elif variable == 't':
                        values = -terrain * 20 + day
                    values = values.astype('float32')
                    values[x < .1] = -9999
                    values[(x >= .1) & (x < .2)] = 0
                    target = folder / f'{variable}-{grid}_{when:%Y%m%dT%H%M%S}.tiff'
                    with rasterio.open(target, 'w', driver='GTiff', width=size, height=size, count=1,
                                       dtype='float32', crs='EPSG:4326', nodata=-9999, transform=transform) as dst:
                        dst.write(values, 1)
            destination = output / 'data' / identity
            catalogue = publish([folder], destination, grid=grid,
                                domain={'id': identity, 'name': name}, ranges={'swe': [0, maximum]},
                                now=datetime(2026, 11, 13, tzinfo=timezone.utc), run_id='synthetic-multisite-demo')
            catalogue['sample_data'] = True
            atomic_json(destination / 'catalog.json', catalogue)
    site_action('configure-site', output, {'version': 1, 'title': 'SnowCast multi-project demo',
        'domains': [{'id': identity, 'name': name, 'catalogue': f'data/{identity}/catalog.json'}
                    for identity, name, *_ in definitions], 'overview_ranges': {}})
    print('Synthetic multi-project demo ready. Open ?site=./demo-site/site.json')


if __name__ == '__main__':
    main()
