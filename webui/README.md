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
The basemap uses Esri's public terrain/imagery tiles and attribution. Confirm
the provider's applicable terms and capacity for your deployment. Font loading
uses Google Fonts with system-font fallbacks; it is independent of data access.

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
- Missing dates and failed point reads produce gaps in charts and CSV. The
  reported change requires a valid first frame and a valid selected frame.
- Playback waits for the incoming viewport to render before changing the
  displayed timestamp. It retains up to three raster layers; point reads run
  with at most three concurrent requests. It pauses in hidden tabs.
- Browsers with WebGL use GPU raster styling. Without WebGL, a Canvas renderer
  styles numeric tiles in a worker and uses the raster's native projection;
  basemap tiles are reprojected to match. Both paths use the same point sampler.
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
