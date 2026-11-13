# CanSWE snapshot

`canswe-v8.zip` is a derived, reproducible static snapshot for the SnowCast
station overlay. It contains a small station index and 750 individually gzipped
station histories/seasonal summaries in the bounding box
`[-132, 46.4, -109.8, 56]`. Locally regenerated bundles can cover any set of
configured projects. The viewer further filters locations to each project's
catalogue bounds. The archive is extracted locally by `scripts/unpack_canswe.py` before
development and production builds; the browser only requests the index and the
selected station's file, never the archive.

Source: Vionnet, V., Mortimer, C., Brady, M., Arnal, L., and Brown, R. (2026),
Canadian historical Snow Water Equivalent dataset (CanSWE, 1928–2025), v8.
https://doi.org/10.5281/zenodo.19075529

Methods: Vionnet et al. (2021), Earth System Science Data, 13, 4603–4619.
https://doi.org/10.5194/essd-13-4603-2021

Original NetCDF: `CanSWE-CanEEN_1928-2025_v8.nc`, MD5
`d7eb41a9cbbce88ff399185402826a44`. Data coverage ends 2025-07-31; station
records have individual start/end dates. This is not a real-time data source.

## Redistribution and attribution

The source NetCDF declares the Open Government Licence – Canada:
https://open.canada.ca/en/open-government-licence-canada

This western subset contains British Columbia, Alberta, Meteorological Service
of Canada, Canadian Rockies Hydrological Observatory, Changing Cold Regions
Network, and Saskatchewan observations. Provider names and station IDs are
preserved, and the UI links to the dataset, methods paper, and licence.
The source's separately licensed Hydro-Québec records are not in this subset;
the converter rejects them if bounds are expanded without reviewing licensing.

## Scientific processing

- `snw` is kg m⁻², numerically equal to mm SWE; `snd` is metres. Original valid
  float32 values are preserved as numbers, missing/masked values as JSON null.
  Both agency flags and CanSWE QC flags are retained independently.
- Observation tuples are `[date, swe_mm, depth_m, agency_swe, agency_depth,
  qc_swe, qc_depth]`. Dates are reported calendar dates, without an invented
  measurement time. Explicitly flagged missing records remain in CSV downloads.
- Snow seasons run August 1 through July 31. Historical reference uses all
  available station years, with actual period and contributing count displayed.
- Each calendar month is split into days 1–15 and 16–end. Each snow year
  contributes its median within that bin; the 25th, 50th, and 75th percentiles
  are then calculated across those yearly medians (NumPy linear quantiles).
  At least ten contributing years are required for a range. Sparse bins retain
  individual year medians; no bands/lines are interpolated across absent bins.
- Summaries exclude CanSWE QC flags and agency flags A/C (sampling problems),
  E (estimated), G (measurement displaced >1 km), M (missing), and Y (uncertain
  date). B (outside nominal survey period), P (patches), R (revised), and T
  (trace) are retained. This is an explicit product choice, not a claim that
  all flagged original observations are invalid.
- Feb 29 shares Feb 28's position only on the seasonal chart axis. Original
  dates are unchanged. Direct model/observation table matches require the same
  calendar date; uncertain dates are not matched. Model timestamps are UTC.
- Comparison samples the existing full-resolution COG pixel at the station.
  It does not search for a nearby valid pixel or correct for elevation/land-cover
  differences. Snow courses and grid cells have different spatial support.

## Reproduce / update

Download the pinned NetCDF from the dataset record, then from the repository
root install the runner and regenerate for all projects selected by your site:

```bash
python -m pip install -e .
snowcast site prepare-canswe sites/snowcast.json \
  --source /path/to/CanSWE-CanEEN_1928-2025_v8.nc \
  --bundle webui/data/canswe-v8.zip
cd webui
npm run build
```

Every selected project needs a locally published catalogue. The converter uses
those WGS84 bounding rectangles, not the site's combined bounding rectangle or
projected grid coordinates, and includes a station only once when domains
overlap. It reports each project's station count and stores IDs/names/bounds in
the derived index. This is bounding-box selection, not exact mesh-mask clipping.
Missing catalogues or a failed conversion leave the existing bundle unchanged.
See the [site guide](../../sites/README.md#refresh-canswe-when-adding-a-project)
for local publication and deployment. The command makes no network requests.

To reproduce the original western subset, the checkout convenience command
`python scripts/prepare_canswe.py /path/to/CanSWE-CanEEN_1928-2025_v8.nc` still
works after installing the runner. It also accepts an explicit geographic
`--bounds WEST SOUTH EAST NORTH`. Reusable conversion code lives in
`snowcast_runner/canswe.py`; the site command works from an installed wheel
without the checkout.

The converter verifies the source checksum and units. A new release requires
reviewing its schema, changes, dates, licences, and updating pinned metadata
before regenerating. Only refreshes require netCDF4; regular app builds use
Python's standard library and the committed snapshot, without contacting Zenodo.
Histories have content-versioned URLs and are written before the index. Keep
old deployed history files while clients may still hold an earlier index.

The bundle is about 6.3 MB; the plain station index is about 242 KB and the
largest selected history is about 126 KB compressed. Station files use explicit
gzip plus browser DecompressionStream; they also work when the web server sends
Content-Encoding: gzip and fetch has already decompressed the body. Existing
modern browser requirements apply. No TIFF conversion or PNG generation is involved.
