"""Generate small synthetic COGs for UI development; never used as live fallback."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_bounds

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from postprocess.publish_cogs import publish, atomic_json


def main():
    output = ROOT / "webui/public/demo"
    size = 768
    transform = from_bounds(-116.65, 50.66, -114.77, 51.79, size, size)
    grid = f"{transform.a}x{-transform.e}"
    y, x = np.mgrid[0:size, 0:size] / size
    ridges = np.sin(31 * (x + .65 * y)) * .5 + np.sin(74 * (x + .72 * y)) * .16
    texture = np.sin(x * 139 + np.cos(y * 61)) * np.cos(y * 131) * .13
    valley = np.exp(-((y - (.9 - .8 * x)) / .055) ** 2)
    terrain = np.clip(.5 + ridges + texture - .8 * valley, 0, 1)
    mask = ((x - .5) / .48) ** 2 + ((y - .5) / .47) ** 2 > 1
    start = datetime(2026, 10, 27, 23, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        for day in range(10):
            when = start + timedelta(days=day)
            for variable in ["swe", "snowdepthavg", "t"]:
                values = terrain * (185 + day * 13) + np.sin(day * .7) * 12
                if variable == "snowdepthavg": values = np.maximum(values, 0) / 280
                elif variable == "t": values = 4 - terrain * 22 - day * .55
                else: values = np.maximum(values, 0)
                values = values.astype("float32"); values[mask] = -9999
                path = folder / f"{variable}-{grid}_{when:%Y%m%dT%H%M%S}.tiff"
                with rasterio.open(path, "w", driver="GTiff", width=size, height=size, count=1,
                                   dtype="float32", crs="EPSG:4326", nodata=-9999,
                                   transform=transform) as dst:
                    dst.write(values, 1)
        catalogue = publish([folder], output, grid=grid, run_id="synthetic-ui-demo", now=start + timedelta(days=9, hours=1))
        catalogue["sample_data"] = True
        atomic_json(output / "catalog.json", catalogue)
    print("Synthetic demo ready. Open the viewer with ?demo=1")


if __name__ == "__main__": main()
