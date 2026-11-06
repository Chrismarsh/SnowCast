"""Publish numeric COGs and an atomic, rolling catalogue on an ordinary disk.

Run after chm_ugrid2grid. The web server only needs to serve static files.
Input TIFFs and the existing AEP/Leaflet products are never modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import warnings
import xml.etree.ElementTree as ET

import numpy as np
import rasterio
from rasterio.shutil import copy as raster_copy
from rasterio.warp import transform_bounds

VARIABLES = {
    "swe": {"label": "SWE", "title": "Snow water equivalent", "unit": "mm", "range": [0, 400], "palette": "snow"},
    "snowdepthavg": {"label": "Snow depth", "title": "Snow depth", "unit": "m", "range": [0, 2], "palette": "snow"},
    "t": {"label": "Temperature", "title": "Air temperature", "unit": "°C", "range": [-25, 10], "palette": "temperature"},
}
PATTERN = re.compile(r"^(?P<variable>swe|snowdepthavg|t)-[^_]+_(?P<time>\d{8}T\d{6})\.tiff?$", re.I)
UTC = timezone.utc
# Include the encoding in immutable asset identities, independently of the input
# hash. Older publications must be rebuilt even when the source TIFF is unchanged.
COG_ENCODING = "float32-v1"


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".catalog-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def convert(source: Path, destination: Path) -> dict:
    """Publish Float32 numeric data on the source grid with averaged overviews."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(source) as src:
        if src.count != 1 or src.crs is None:
            raise ValueError(f"Expected a single numeric band with a CRS: {source}")
        if src.dtypes[0].startswith("complex"):
            raise ValueError(f"Complex raster values are unsupported: {source}")
        epsg = src.crs.to_epsg()
        if epsg is None:
            raise ValueError(f"An EPSG-identifiable CRS is required: {source}")
        bounds = list(transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21))
        if not all(math.isfinite(v) for v in bounds):
            raise ValueError(f"Invalid geographic bounds: {source}")
        transform = list(src.transform)[:6]
        nodata = src.nodata
        if nodata is not None and math.isfinite(nodata):
            if abs(nodata) > float(np.finfo(np.float32).max):
                raise ValueError(f"Nodata is outside the Float32 range: {source}")
            nodata = float(np.float32(nodata))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            proj4 = src.crs.to_proj4()
        metadata = {
            "projection": f"EPSG:{epsg}", "proj4": proj4,
            "bounds": bounds, "shape": [src.height, src.width], "transform": transform,
            "nodata": nodata if nodata is None or math.isfinite(nodata) else "NaN",
            "scale": src.scales[0], "offset": src.offsets[0], "dtype": "float32",
        }
    if not destination.exists():
        temporary = destination.with_suffix(".partial.tif")
        virtual = destination.with_suffix(".source.vrt")
        try:
            # A VRT casts blocks while GDAL copies them: no full-size intermediate
            # TIFF, reprojection, or whole-raster NumPy allocation is required.
            # Preserve the source's masks, scale/offset and other band metadata.
            raster_copy(source.resolve(), virtual, driver="VRT")
            tree = ET.parse(virtual)
            band = tree.getroot().find("VRTRasterBand")
            band.set("dataType", "Float32")
            nodata_element = band.find("NoDataValue")
            if nodata_element is not None:
                nodata_element.text = str(nodata)
            tree.write(virtual, encoding="utf-8", xml_declaration=True)
            raster_copy(virtual, temporary, driver="COG", compress="DEFLATE",
                        blocksize=512, predictor="YES", overview_resampling="AVERAGE",
                        OVERVIEWS="IGNORE_EXISTING", BIGTIFF="IF_SAFER")
            with rasterio.open(temporary) as cog:
                if cog.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") != "COG":
                    raise RuntimeError(f"GDAL did not produce a COG: {source}")
                if cog.dtypes != ("float32",):
                    raise RuntimeError(f"GDAL did not produce Float32 data: {source}")
                if cog.crs.to_epsg() != epsg or list(cog.transform)[:6] != transform:
                    raise RuntimeError(f"Georeferencing changed during conversion: {source}")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
            virtual.unlink(missing_ok=True)
    return metadata


def publish(inputs: list[Path], output: Path, days: int = 10, run_id: str | None = None,
            base_url: str | None = None, now: datetime | None = None) -> dict:
    if not 1 <= days <= 366:
        raise ValueError("days must be between 1 and 366")
    now = now or datetime.now(UTC)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # One publisher at a time; flock is released even after a killed process.
    import fcntl
    with (output / ".publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        catalogue_path = output / "catalog.json"
        previous = json.loads(catalogue_path.read_text()) if catalogue_path.exists() else {}
        if previous and previous.get("version") != 1:
            raise ValueError("Unsupported existing catalogue version")
        assets = {v["id"]: {a["datetime"]: a for a in v["assets"]}
                  for v in previous.get("variables", [])}
        candidates = {}
        # Later input directories take precedence, so archive first / current last.
        for directory in inputs:
            for path in sorted(Path(directory).glob("*")):
                match = PATTERN.match(path.name)
                if not match or not path.is_file():
                    continue
                stamp = datetime.strptime(match["time"], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
                candidates[(match["variable"].lower(), iso(stamp))] = path
        times = [stamp for _, stamp in candidates] + [s for group in assets.values() for s in group]
        if not times:
            raise ValueError("No timestamped SnowCast TIFFs or existing catalogue assets found")
        latest = datetime.fromisoformat(max(times).replace("Z", "+00:00"))
        # Ten calendar dates including latest, rather than ten files or ten runs.
        cutoff = (latest - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_iso = iso(cutoff)
        for (variable, stamp), source in sorted(candidates.items()):
            if stamp < cutoff_iso:
                continue
            digest = sha256(source)
            current = assets.setdefault(variable, {}).get(stamp)
            if (current and current.get("source_sha256") == digest
                    and current.get("cog_encoding") == COG_ENCODING and (output / current["path"]).exists()):
                continue
            compact = stamp.replace("-", "").replace(":", "").replace("Z", "")
            identity = f"{compact}-{digest[:20]}-{COG_ENCODING}"
            relative = f"cogs/{variable}/{identity}.tif"
            metadata = convert(source, output / relative)
            assets[variable][stamp] = {
                "id": f"{variable}-{identity}", "path": relative,
                "href": relative, "datetime": stamp, "run_id": run_id,
                "published_at": iso(now), "source_sha256": digest, "cog_encoding": COG_ENCODING, **metadata,
            }
        variables = []
        for variable, settings in VARIABLES.items():
            retained = [a for t, a in sorted(assets.get(variable, {}).items()) if t >= cutoff_iso]
            for asset in retained:
                if not (output / asset["path"]).is_file():
                    raise FileNotFoundError(f"Catalogue asset missing: {asset['path']}")
                asset["href"] = f"{base_url.rstrip('/')}/{asset['path']}" if base_url else asset["path"]
            if retained:
                variables.append({"id": variable, **settings, "assets": retained})
        all_bounds = [a["bounds"] for v in variables for a in v["assets"]]
        catalogue = {
            "version": 1, "title": "Upper Bow River", "generated_at": iso(now),
            "latest_time": iso(latest), "window_days": days, "sample_data": False,
            "bounds": [min(b[0] for b in all_bounds), min(b[1] for b in all_bounds),
                       max(b[2] for b in all_bounds), max(b[3] for b in all_bounds)],
            "variables": variables,
        }
        atomic_json(catalogue_path, catalogue)
        return catalogue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True,
                        help="TIFF directory; repeat with archive first and current last")
    parser.add_argument("--output", type=Path, required=True, help="Published static-data directory")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--run-id", help="Actual model run identifier, if known; not inferred from file time")
    parser.add_argument("--base-url", help="Optional absolute HTTPS base URL of the data directory")
    args = parser.parse_args()
    catalogue = publish(args.input, args.output, args.days, args.run_id, args.base_url)
    print(f"Published {sum(len(v['assets']) for v in catalogue['variables'])} assets to {args.output / 'catalog.json'}")


if __name__ == "__main__":
    main()
