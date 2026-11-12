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
import sys
import warnings
import xml.etree.ElementTree as ET

import numpy as np
import rasterio
from rasterio.shutil import copy as raster_copy
from rasterio.warp import transform_bounds

from .cog_store import atomic_json, cleanup_locked, make_assets_public, store_lock

VARIABLES = {
    "swe": {"label": "SWE", "title": "Snow water equivalent", "unit": "mm", "range": [0, 400], "palette": "snow"},
    "snowdepthavg": {"label": "Snow depth", "title": "Snow depth", "unit": "m", "range": [0, 2], "palette": "snow"},
    "t": {"label": "Temperature", "title": "Air temperature", "unit": "°C", "range": [-25, 10], "palette": "temperature"},
}
PATTERN = re.compile(r"^(?P<variable>swe|snowdepthavg|t)-(?P<grid>[^_]+)_(?P<time>\d{8}T\d{6})\.tiff?$", re.I)
DEFAULT_GRID = "0.001x0.001"
UTC = timezone.utc
# Include the encoding in immutable asset identities, independently of the input
# hash. Older publications must be rebuilt even when the source TIFF is unchanged.
COG_ENCODING = "float32-v1"


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def hydrological_year_start(latest: datetime):
    """September 1 of the hydrological year containing the latest model date (UTC)."""
    day = latest.astimezone(UTC).date()
    return day.replace(year=day.year if day.month >= 9 else day.year - 1, month=9, day=1)


def retained_times(times, latest, days, weekly_days=None):
    """Daily outputs and Monday–Sunday weekly snapshots within the current hydrological year.

    An optional weekly_days cap can shorten this history, but never extend it
    before September 1. Zero disables weekly snapshots; None keeps the full year.
    """
    latest_day = latest.astimezone(UTC).date()
    daily_cutoff = latest_day - timedelta(days=days - 1)
    oldest = hydrological_year_start(latest)
    if weekly_days is not None:
        oldest = max(oldest, latest_day - timedelta(days=max(days, weekly_days) - 1))
    daily = {}
    for stamp in sorted(times):
        day = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(UTC).date()
        if oldest <= day <= latest_day:
            daily[day] = stamp
    selected = {stamp for day, stamp in daily.items() if day >= daily_cutoff}
    if weekly_days != 0:
        weeks = {}
        for day, stamp in sorted(daily.items()):
            weeks[day - timedelta(days=day.weekday())] = stamp
        selected.update(weeks.values())
    return selected


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dataset_sha256(path: Path) -> str:
    """Identify the TIFF and GDAL-reported sidecars, independent of its directory."""
    path = path.resolve()
    with rasterio.open(path) as src:
        files = {Path(name).resolve() for name in src.files} | {path}
    # Hash the manifest as well as the bytes: adding/removing a .msk or .aux.xml
    # must invalidate the COG even when the TIFF itself has not changed.
    manifest = sorted((os.path.relpath(name, path.parent), sha256(name)) for name in files)
    return hashlib.sha256(json.dumps(manifest, separators=(",", ":")).encode()).hexdigest()


def grid_resolution(grid: str) -> tuple[float, float]:
    try:
        dx, dy = map(float, grid.split("x"))
        if all(math.isfinite(v) and v > 0 for v in (dx, dy)):
            return dx, dy
    except ValueError:
        pass
    raise ValueError("grid must contain two positive resolutions, e.g. 0.001x0.001")


def matches_resolution(asset: dict, resolution: tuple[float, float]) -> bool:
    a, b, _, d, e, _ = asset["transform"]
    dx, dy = resolution
    # Filenames name the nominal spacing. Fitting domain bounds to integer
    # dimensions produces ~0.00100005 degrees in the live 0.001-degree grid.
    # This tolerance only identifies resolution; date alignment remains strict.
    return (b == 0 and d == 0 and math.isclose(a, dx, rel_tol=1e-3)
            and math.isclose(e, -dy, rel_tol=1e-3))


def validate_alignment(assets: list[dict], variable: str) -> None:
    """Use the same cell-alignment tolerance as the browser's date differences."""
    reference = assets[-1]
    tolerance = max(abs(reference["transform"][0]), abs(reference["transform"][4])) * 1e-6
    for asset in assets:
        if (asset["projection"] != reference["projection"] or asset["shape"] != reference["shape"]
                or any(abs(a - b) > tolerance for a, b in zip(asset["transform"], reference["transform"]))):
            raise ValueError(f"Unaligned {variable} grids at {asset['datetime']} and {reference['datetime']}; "
                             "rebuild these dates on the same grid before publishing")


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
                        # Keep square 512px blocks: OpenLayers' strip fallback
                        # can override rasterRequests.ts's direct-range option.
                        blocksize=512, predictor="YES", overview_resampling="AVERAGE",
                        OVERVIEWS="IGNORE_EXISTING", BIGTIFF="IF_SAFER")
            with rasterio.open(temporary) as cog:
                if cog.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") != "COG":
                    raise RuntimeError(f"GDAL did not produce a COG: {source}")
                if cog.dtypes != ("float32",):
                    raise RuntimeError(f"GDAL did not produce Float32 data: {source}")
                if cog.block_shapes != [(512, 512)]:
                    raise RuntimeError(f"Unexpected COG tile layout: {source}")
                if cog.crs.to_epsg() != epsg or list(cog.transform)[:6] != transform:
                    raise RuntimeError(f"Georeferencing changed during conversion: {source}")
            temporary.chmod(0o644)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
            virtual.unlink(missing_ok=True)
    return metadata


def publish(inputs: list[Path], output: Path, days: int = 10, run_id: str | None = None,
            base_url: str | None = None, now: datetime | None = None,
            grid: str = DEFAULT_GRID, weekly_days: int | None = None,
            domain: dict | None = None, ranges: dict | None = None) -> dict:
    if not 1 <= days <= 366:
        raise ValueError("days must be between 1 and 366")
    if weekly_days is not None and not 0 <= weekly_days <= 366:
        raise ValueError("weekly_days must be None or between 0 and 366")
    resolution = grid_resolution(grid)
    for variable, span in (ranges or {}).items():
        if variable not in VARIABLES or len(span) != 2 or not all(math.isfinite(v) for v in span) or span[0] >= span[1]:
            raise ValueError('Invalid variable colour range')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # Also held by the uploader, so cleanup cannot remove its snapshot's files.
    with store_lock(output):
        catalogue_path = output / "catalog.json"
        previous = json.loads(catalogue_path.read_text()) if catalogue_path.exists() else {}
        if previous and previous.get("version") != 1:
            raise ValueError("Unsupported existing catalogue version")
        if previous and (previous.get('domain') or {}).get('id') != (domain or {}).get('id'):
            raise ValueError('Publication directory belongs to a different domain')
        assets = {}
        for variable in previous.get("variables", []):
            retained = {a["datetime"]: a for a in variable["assets"] if matches_resolution(a, resolution)}
            omitted = len(variable["assets"]) - len(retained)
            if omitted:
                warnings.warn(f"Omitting {omitted} previously published {variable['id']} assets outside grid {grid}")
            assets[variable["id"]] = retained
        candidates = {}
        # Later input directories take precedence, so archive first / current last.
        for directory in inputs:
            for path in sorted(Path(directory).glob("*")):
                match = PATTERN.match(path.name)
                if not match or match["grid"] != grid or not path.is_file():
                    continue
                stamp = datetime.strptime(match["time"], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
                candidates[(match["variable"].lower(), iso(stamp))] = path
        times = [stamp for _, stamp in candidates] + [s for group in assets.values() for s in group]
        if not times:
            raise ValueError(f"No timestamped SnowCast TIFFs or existing catalogue assets found for grid {grid}")
        latest = datetime.fromisoformat(max(times).replace("Z", "+00:00"))
        year_start = hydrological_year_start(latest)
        # At the September rollover, do not fill the recent window with dates
        # from the previous hydrological year (including missing UI slots).
        window_days = min(days, (latest.astimezone(UTC).date() - year_start).days + 1)
        selected = {variable: retained_times(
            set(assets.get(variable, {})) | {stamp for name, stamp in candidates if name == variable},
            latest, days, weekly_days if variable in ("swe", "snowdepthavg") else 0,
        ) for variable in VARIABLES}
        for (variable, stamp), source in sorted(candidates.items()):
            if stamp not in selected[variable]:
                continue
            digest = dataset_sha256(source)
            current = assets.setdefault(variable, {}).get(stamp)
            if (current and current.get("source_sha256") == digest
                    and current.get("cog_encoding") == COG_ENCODING and (output / current["path"]).exists()):
                continue
            compact = stamp.replace("-", "").replace(":", "").replace("Z", "")
            identity = f"{compact}-{digest[:20]}-{COG_ENCODING}"
            relative = f"cogs/{variable}/{identity}.tif"
            metadata = convert(source, output / relative)
            if not matches_resolution(metadata, resolution):
                raise ValueError(f"Raster resolution does not match grid {grid}: {source}")
            assets[variable][stamp] = {
                "id": f"{variable}-{identity}", "path": relative,
                "href": relative, "datetime": stamp, "run_id": run_id,
                "published_at": iso(now or datetime.now(UTC)), "source_sha256": digest, "cog_encoding": COG_ENCODING, **metadata,
            }
        variables = []
        for variable, settings in VARIABLES.items():
            retained = [a for t, a in sorted(assets.get(variable, {}).items()) if t in selected[variable]]
            for asset in retained:
                if domain:
                    asset['id'] = f'{domain["id"]}:{variable}:{Path(asset["path"]).stem}'
                if not (output / asset["path"]).is_file():
                    raise FileNotFoundError(f"Catalogue asset missing: {asset['path']}")
                asset["href"] = f"{base_url.rstrip('/')}/{asset['path']}" if base_url else asset["path"]
                asset["bytes"] = (output / asset["path"]).stat().st_size
            if retained:
                validate_alignment(retained, variable)
                variables.append({"id": variable, **settings,
                                  "range": (ranges or {}).get(variable, settings['range']), "assets": retained})
        all_bounds = [a["bounds"] for v in variables for a in v["assets"]]
        # Conversion/backfill can take hours; grace starts when this catalogue
        # actually replaces the old references, not when conversion started.
        now = now or datetime.now(UTC)
        generated = now.astimezone(UTC)
        if previous:
            prior = datetime.fromisoformat(previous["generated_at"].replace("Z", "+00:00"))
            # The store lock serializes publications; retain that order even if
            # the clock repeats or moves backwards between consecutive runs.
            generated = max(generated, prior + timedelta(microseconds=1))
        catalogue = {
            "version": 1, "title": "SnowCast model domain",
            "generated_at": generated.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "latest_time": iso(latest), "window_days": window_days, "sample_data": False, "grid": grid,
            "retention": {"daily_days": days, "weekly_days": weekly_days,
                          "hydrological_year_start": year_start.isoformat(),
                          "weekly_variables": ["swe", "snowdepthavg"], "week_starts": "Monday"},
            "storage_bytes": sum(a["bytes"] for v in variables for a in v["assets"]),
            "bounds": [min(b[0] for b in all_bounds), min(b[1] for b in all_bounds),
                       max(b[2] for b in all_bounds), max(b[3] for b in all_bounds)],
            "variables": variables,
        }
        if domain:
            catalogue.update(domain=domain, title=domain['name'])
        make_assets_public(output, catalogue)
        atomic_json(catalogue_path, catalogue)
        try:
            cleanup_locked(output, now=now.timestamp())
        except Exception as error:
            warnings.warn(f"Catalogue published; COG cleanup deferred: {error}")
        return catalogue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True,
                        help="TIFF directory; repeat with archive first and current last")
    parser.add_argument("--output", type=Path, required=True, help="Published static-data directory")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--weekly-days", type=int,
                        help="Optional history cap within the current September–August hydrological year "
                             "(default: full hydrological year; 0 disables weekly SWE/SD snapshots)")
    parser.add_argument("--grid", default=DEFAULT_GRID,
                        help="Source filename grid and pixel spacing in CRS units (default: %(default)s)")
    parser.add_argument("--run-id", help="Actual model run identifier, if known; not inferred from file time")
    parser.add_argument("--base-url", help="Optional absolute HTTPS base URL of the data directory")
    args = parser.parse_args()
    catalogue = publish(args.input, args.output, args.days, args.run_id, args.base_url,
                        grid=args.grid, weekly_days=args.weekly_days)
    print(f"Published {sum(len(v['assets']) for v in catalogue['variables'])} assets to {args.output / 'catalog.json'}")


if __name__ == "__main__":
    main()
