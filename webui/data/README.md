# CanSWE subset

Observation subsets are generated during project publication from a verified,
locally cached source. The registry defines source release, attribution and
selection settings. The publisher selects each project's WGS84 bounds plus its
nearby radius (default 100 km), then merges overlapping selections. The viewer
filters stations to loaded project bounds plus that radius. Histories are fetched
only when a station is selected; the browser never downloads the source NetCDF.

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

This subset includes western Canadian observations and stations near TVC in the
Northwest Territories. Provider names and station IDs are
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

## Download and publish

There is no committed subset. The installed `observations.json` registry pins
the source release/checksum and carries the display and attribution settings.

```bash
snowcast download-data canswe
snowcast publish sites/snowcast.json --project tvc
```

Sources stay in the shared local cache. Publish subsets by each project's geographic
bounds with the configured nearby radius (default 100 km), deduplicates overlap,
and uploads histories before the public registry. Outside-domain stations remain
observations only. UI builds do not touch observations. See the
[site guide](../../sites/README.md#observation-datasets) for cache overrides,
offline imports, migration and the common station format.

The converter verifies source checksum and units. New releases require reviewing
the schema, flags and licensing before changing the registry. Compressed histories
are decoded by the browser on selection, including when HTTP already decompresses
them. Missing values stay null, and the original scientific rules above are unchanged.
