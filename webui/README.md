# SnowCast explorer (v3)

A static Svelte/TypeScript + OpenLayers viewer for numeric Cloud Optimized
GeoTIFFs. It provides daily playback, a full-resolution point history, COG URL
and local-file import, point CSV downloads, shareable links, and a responsive
map/inspector layout. There is no application server, database, S3 dependency,
or connection from the public browser to the model's compute environment.

![Working explorer with explicitly labelled synthetic COG data](docs/explorer-demo-20261105.jpg)

## How the COGs are generated

The existing model pipeline remains:

1. CHM writes UGRID output.
2. `chm_ugrid2grid` conservatively regrids SWE, snow depth, and temperature.
3. `postprocess/publish_cogs.py` copies those numeric TIFFs using GDAL's COG
   driver (via Rasterio), adding internal 512-pixel tiles, DEFLATE compression,
   and average overviews. It retains the source grid, dtype, scale/offset,
   nodata, and full-resolution values. Only the display overviews are averaged.
4. The publisher writes immutable, timestamp/content-versioned files and an
   atomic `catalog.json`. The browser styles the numeric values at runtime.

An equivalent single-file conversion using your existing GDAL installation:

```bash
gdal_translate input.tiff output.cog.tif -of COG \
  -co COMPRESS=DEFLATE -co PREDICTOR=YES -co BLOCKSIZE=512 \
  -co OVERVIEW_RESAMPLING=AVERAGE -co BIGTIFF=IF_SAFER
```

Do not colourize the TIFF before this step. A COG containing RGB colours does
not contain the numeric values needed for point queries. A `.tif` suffix alone
also does not establish that a file is a COG.

## Hosting on an ordinary disk

Yes: keep files on a normal filesystem and serve them with Nginx or Apache.
The browser requires an HTTP(S) URL, not a filesystem path. A disk on an HPC
login node is sufficient only if a web server can expose it; otherwise use the
included rsync publisher to copy the COGs onto the web host's disk.

The important server behaviour is **actual byte-range GET support**: a request
for `Range: bytes=0-1023` must return `206 Partial Content` and those bytes.
`Accept-Ranges: bytes` alone is not proof. Do not gzip/brotli-compress TIFFs in
HTTP responses. Allow CORS if the viewer and data have different origins.

Suggested layout, with the compiled application and data deployed separately:

```text
/var/www/html/v3/index.html
/var/www/html/v3/assets/...
/var/www/html/v3/data/catalog.json
/var/www/html/v3/data/cogs/swe/20261105T230000-<hash>.tif
```

Nginx configuration for a directory outside the document root:

```nginx
# Inside your HTTPS server block. alias points to an ordinary disk directory.
location /snowcast-data/ {
    alias /srv/snowcast/webdata/;
    gzip off;
    add_header Cache-Control "public, max-age=31536000, immutable" always;
    # Only needed if the UI is on a different origin; these data are public.
    add_header Access-Control-Allow-Origin "*" always;
    add_header Access-Control-Expose-Headers "Content-Range, Accept-Ranges, Content-Length" always;
}
location = /snowcast-data/catalog.json {
    alias /srv/snowcast/webdata/catalog.json;
    add_header Cache-Control "no-cache" always;
    add_header Access-Control-Allow-Origin "*" always;
}
```

Nginx normally supports ranges for static files without an extra directive.
Disable any inherited third-party HTTP compression for `.tif` as well. With
Apache, use `Alias` + a read-only `<Directory>` configuration and the same
cache/CORS response headers; its static-file handler supports byte ranges.
Never expose the simulation's checkpoint or credential directories.

Check the deployed endpoint:

```bash
python scripts/check_cog_host.py https://www.snowcast.ca/v3/data/cogs/swe/FILE.tif
# If data and viewer use different origins:
python scripts/check_cog_host.py https://data.example/snowcast-data/cogs/swe/FILE.tif \
  --origin https://www.snowcast.ca
```

## Build and deploy

Use Node 22.12+ (Node 24 recommended) to build; Node is not needed on the server.

```bash
cd webui
npm ci
npm run check
npm test
npm run build
```

Upload `dist/` to `/v3/`. Keep `data/` separate from application synchronization.
For example, from `webui/`:

```bash
rsync -rt --exclude=data/ --exclude=demo/ dist/ USER@HOST:/var/www/html/v3/
```

Do not point the legacy `/v2/` rsync mirror at `/v3/`, and do not blindly use
`--delete` over a directory containing data. The existing v2 viewer is untouched.
The application uses relative asset URLs and works in a `/v3/` subdirectory.
By default it requests `./data/catalog.json`. For an external data server, use:

```text
https://www.snowcast.ca/v3/?catalog=https%3A%2F%2Fdata.example%2Fsnowcast-data%2Fcatalog.json
```

Asset URLs inside the catalogue are resolved relative to the catalogue itself.
Use the trailing slash on `/v3/` (or configure the web server's directory redirect).
OpenStreetMap is the default basemap. The layers button opens a picker for
OpenStreetMap, Esri topographic, Esri satellite, or None (model data only).
The choice is saved in this browser and in the page URL; an explicit
`?basemap=osm`, `terrain`, `satellite`, or `none` takes precedence over the saved
choice. `?basemap=auto` resets to OpenStreetMap. Switching basemaps does not
reload the COG layer, reset the date, or clear the selected point.

The OpenStreetMap source uses the official HTTPS tile endpoint, visible linked
attribution, normal browser caching/referrer behavior, and no basemap prefetch.
Follow the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/);
the community tile service is best-effort and is not an offline/bulk tile source.
Check the chosen provider's capacity and terms for your deployment. Selecting
None removes the basemap source so it schedules no new basemap requests.
Font loading uses Google Fonts with system-font fallbacks; it is independent
of data access. A different basemap provider may improve a particular network
path, but is not a measured guarantee of faster loading on every device.

## Publish the initial ten-day window

From the repository root, with Rasterio/GDAL available (already in `spack.yaml`):

```bash
python postprocess/publish_cogs.py \
  --input postprocess/archive_tiff --input postprocess/tiff \
  --output postprocess/webdata --days 10
```

The last input directory wins if archive and current directories contain the
same variable/time. The publisher merges prior published assets, so incremental
two-record exports still build a ten-day history. It anchors the window to the
latest available simulation date, including that date and the previous nine
UTC dates; missing days remain missing. Old files are not silently converted
into observations. Model run IDs can be supplied with `--run-id` if known;
publication time is recorded separately and is never passed off as run time.

If the data directory is directly served by your web server, publication is
complete. To copy it to another host:

```bash
python webupload/v3.py --data postprocess/webdata \
  --host USER@HOST --directory /var/www/html/v3/data
```

This copies referenced COGs first, then transfers a catalogue snapshot and
atomically renames it on the remote filesystem. It does not update live COGs in
place and does not delete older files. Use a single upload process per destination.

For automatic publishing after each model run, set in `config_hrdps_west.py`:

```python
settings['webui_enabled'] = True
settings['webui_upload_host'] = 'USER@HOST'  # omit for directly served local disk
settings['webui_upload_dir'] = '/var/www/html/v3/data'
```

This is opt-in until the real host is configured. Model physics, output cadence,
checkpoint retention, existing AEP exports, and the legacy v2 path are unchanged.

The catalogue retains ten days, but immutable files on disk are deliberately
not automatically removed. For disk cleanup, remove only files no longer
referenced by the current catalogue **after a grace period of at least 48 hours
from when they became unreferenced**, allowing old browser sessions to finish.
Keep long-term scientific archives separately. Do not prune by file creation age
alone; an old file can still be referenced. No original TIFF is deleted.

## Data semantics and limitations

- SWE is in mm, snow depth in m, temperature in °C, following existing SnowCast
  plotting metadata. Verify upstream units when adding a new variable.
- The daily viewer uses the latest valid timestamp in each UTC day. It does
  not silently blend forecast runs. A future forecast-run selector would need
  explicit forecast provenance and lead-time metadata.
- All dates are UTC; there is no inference of “current” from the hour of day.
- Point values come from the containing full-resolution raster cell, with
  affine/CRS transformation, nodata/mask handling, and scale/offset applied.
  They are regridded values, not original CHM triangle values.
- Colours use one fixed range per variable across dates, with nearest-neighbour
  display interpolation. Overviews may aggregate pixels; the point value never
  depends on map zoom. Zero and nodata are distinct.
- SWE, snow depth, and temperature use transparent missing-data pixels in both
  renderers. The WebGL colour expression explicitly checks the validity band
  and the raw nodata sentinel before scaling/colour mapping. Valid zero snow
  and valid temperatures below the legend minimum remain visible.
- Missing dates and failed point reads produce gaps in charts and CSV. The
  reported change requires a valid first frame and a valid selected frame.
- Playback waits for the selected raster's viewport to render before changing
  the displayed timestamp. Basemap loading does not hold back a ready raster.
  Direct byte-range reads bypass geotiff.js 3.1's shared block cache: a live
  zoomed SWE check reproduced an internal `AggregateError: Request failed`
  after every HTTP request had succeeded, with required blocks missing from
  that cache. Decoded OpenLayers tile caching remains enabled.
  Remote raster range reads share a six-request limit across map frames and
  retry transient network/body failures or HTTP 408/429/500/502/503/504 up to
  twice. Responses must match their requested byte ranges and body lengths;
  a server returning the entire COG or a permanent HTTP error fails explicitly.
  Abandoning a frame cancels its queued transfers and retries. The limit covers
  map COG reads; basemaps and point samples have separate request handling.
  After 15 seconds the viewer shows a slow-loading notice and continues waiting;
  it reports a stall only after 90 seconds without raster loading progress.
  It retains up to three raster layers; point reads run with at most three
  concurrent requests. Playback pauses in hidden tabs.
- Tile errors remain monitored after a frame is displayed, including pan/zoom.
  Canvas rejects an image containing failed tiles rather than displaying those
  tiles as transparent model nodata. It retains the last good layer image while
  reporting the failure. Retry reopens the source, clearing failed tile caches.
- Both renderers keep the Web Mercator map view (EPSG:3857), matching v2.
  WebGL styles and reprojects numeric raster tiles. Canvas styles native-grid
  values in a worker, then reprojects the resulting RGBA image using Canvas 2D;
  it does not invoke GPU float-data reprojection. Both paths use the same
  full-resolution point sampler and preserve transparent missing pixels.
- Automatic rendering retries a WebGL tile failure or 90-second loading stall
  once with Canvas, retaining the map view, selected frame, and point. It saves
  Canvas as this browser's preference only after the retry renders successfully.
  Other devices keep their own preference. A failure in both modes is reported.
  An identified HTTP failure is reported directly rather than retried with a
  different renderer.
- COG import supports single-band numeric data with EPSG:4326, EPSG:3857, and
  standard WGS84 UTM definitions. Other EPSG projections work through a
  catalogue containing `proj4`. Multiple imported filenames require timestamps.
  The latest ten daily dates are shown; imported layers are session-local.
- Local files need no server; a remote URL requires range support and CORS.
- Share links preserve variable, selected date, and point. The exact history
  can expire when it leaves the rolling catalogue; download CSV for a snapshot.
- Error states never silently substitute synthetic data.

## Development and validation

```bash
python -m pip install rasterio numpy pytest
python -m pytest -q tests
cd webui
npm ci
npm run demo
npm run dev
```

Open the development URL with `?demo=1`. All demo rasters are synthetic and the
viewer displays a prominent label. The demo generator and catalogue use exactly
the same COG publisher as real data. Generated demo files are ignored by git;
exclude `demo/` when deploying the public application.

Before production, run the hosting check and compare a few clicked points
against Rasterio/GDAL samples from your actual rasters, including outside-domain
and nodata cells. Test the actual host with desktop and mobile browsers. Synthetic
fixtures validate functionality, not performance with full-size production data.
The initial browser QA exercised the Canvas fallback (the test browser had no
WebGL), daily playback, point histories, local TIFF and HTTP COG import, CSV
export, share links, and the missing-catalogue state. The ten demo point values
were independently compared with Rasterio. GPU rendering and mobile devices
still need verification on the deployment host.

Loading regressions cover a 35-second response, continuous progress over several
minutes, a genuinely stalled transfer, and cancellation during date changes.
Browser QA also delayed the initial temperature COG response by 35 seconds:
the slow-loading notice appeared, then the frame rendered successfully without
a retry. [Screenshot with synthetic data](docs/temperature-loading-check.jpg).

## Diagnosing slow laptop loading

The initial map now waits for the catalogue and fits its actual domain before
requesting tiles. Previously, WebGL kept the placeholder Upper Bow view even
when the catalogue covered a much larger area. Display rendering is capped at
2× pixel density and four million pixels per map canvas; a resize recomputes
that limit. This affects display detail only, never full-resolution point reads.
Switching away from an unfinished frame aborts its remote COG requests and
disposes that frame instead of allowing abandoned loads to accumulate.

After deploying the rebuilt UI, open **About → Map diagnostics / slow loading**,
or **Loading diagnostics** in a slow-loading/error notice. While the map is
stuck, refresh the snapshot and copy it. It shows the actual rendering path,
viewport/display pixel ratio, projections, COG state, raster rendering state,
the saved/requested renderer preference, any automatic fallback reason, and
separate raster/basemap pending, settled and failed tile counts. After automatic
recovery it also retains the original WebGL failure snapshot. Counts are
per source instance, not percentages of the current viewport; settled tiles
can include requests the renderer no longer needs. Pending raster tiles may
be downloading, decoding or reprojecting, so this is not a network trace.
The report omits URLs, coordinates and GPU identifiers.
It includes the variable/time, actual tile error, and HTTP attempt counters.
`rasterRequests.lastError` records the last failed request attempt (including
ones later recovered), its phase, and HTTP status when available. These distinguish
HTTP/network/body failures from later TIFF decoding or tile-rendering errors.

The dialog offers reversible comparisons (each reloads the page):

- `?detail=low`: cap display density at 1× to compare a lower graphics workload.
- `?renderer=canvas`: use and remember compatibility rendering, keeping the
  Web Mercator view. This can be slower on some machines.
- `?renderer=auto`: reset the saved renderer preference and enable automatic
  recovery. `?renderer=webgl` explicitly forces WebGL without automatic recovery
  for troubleshooting. Explicit URL options override the saved preference.
- `?basemap=none`: remove the basemap to isolate COG loading/rendering. This is
  also available as None in the basemap picker, without reloading the page.

Parameters can be combined; the same links restore automatic behavior. Local
imports must be reopened after a reload. Compare one change at a time, and
compare phone/laptop on the same Wi-Fi without a VPN before attributing a
difference to graphics or the host. The affected laptop loaded successfully
with the earlier native-grid Canvas path, but failed in WebGL with no basemap
requests. That narrows the issue to the rendering paths; it does not establish
a specific GPU-driver or network cause. Canvas now preserves the requested
Mercator view without numeric-data GPU reprojection. The build and automated
tests cover the change; its local preview was blocked in the cloud test browser.
Renderer tests cover remembered choices and one-time recovery. Projection tests
exercise OpenLayers' native-to-Mercator image requests, readiness, and disposal.
A Canvas 2D integration test checks actual output pixels at known geographic
locations (including nodata and valid zero) while rejecting WebGL requests.
Its native Canvas dependency is used only by tests, not shipped to browsers.
Additional regressions cover transient HTTP failures, interrupted/truncated
responses, permanent range errors, queued/retrying request cancellation, and
a failed tile after an initially successful Canvas frame followed by recovery.
Transparency regression checks evaluate the generated colour expression with
OpenLayers, compile it to GLSL, and check Canvas output for missing values,
masked pixels, valid zero snow, and cold temperatures. These are not a substitute
for a visual WebGL check on the affected device.
