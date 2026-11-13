# Several projects on one SnowCast website

A site selects independent project folders; each project still owns its model
configuration, forcing, jobs, checkpoints and postprocessed products. Publishing
one project updates its COG catalogue without running or replacing another
project. The web application is built once and discovers the selected projects
from `site.json` beside `index.html`.

## Configure the site

Copy `snowcast.example.json` to `snowcast.json` and edit it for your installation.
The example assumes you have already created `projects/tvc`; that personal
project is not supplied by this repository. Paths are relative to the **site
configuration file**, or can be absolute. Each entry in `projects` is a project
folder or its `snowcast.json`. IDs and names come from those project manifests.
IDs must be unique. Order is preserved; later projects draw above earlier ones
where their coverage overlaps. There is no built-in list or limit of domains.

`staging` must be outside every project's `work` directory. For SSH publication,
set `deploy.host` to your own SSH destination/alias and `deploy.directory` to the
website root, such as `/var/www/html/v3`. No username is built into the runner.
Omit `deploy` for a local or mounted website. Only project IDs, display names,
catalogue URLs and colour ranges enter the public manifest; local paths and SSH
settings are never published.

From the checkout root:

```bash
snowcast site validate sites/snowcast.json
snowcast site configure sites/snowcast.json --upload
```

`validate` checks configuration without requiring local mesh/forcing files or
starting a job. `configure` installs the selected projects, order and overview
ranges in staging; `--upload` also configures the remote website. It can run
before any project's first publish. Unpublished projects are shown as unavailable.

Only **configure** changes selection/order. After editing the site config, run
it again. Publishers using an old configuration are rejected instead of restoring
removed projects. Removing a project hides it but intentionally keeps its files;
it does not delete model output or other project data.

## Publish each project independently

After that project's `snowcast postprocess` has completed:

```bash
snowcast site publish sites/snowcast.json --project western-cordillera --upload
snowcast site publish sites/snowcast.json --project tvc --upload
```

Omit `--upload` to publish only to staging. Either command can run independently;
the other project keeps its existing catalogue. Repeating a command is safe.
Each store is `data/<project-id>/` and has its own conversion/upload lock and COG
cleanup. A separate site lock protects the shared registry. Uploads transfer and
verify assets before atomically committing the catalogue and registering it.
An interrupted first upload does not advertise an incomplete new domain; retry
the same command. Existing domains keep their last complete published catalogue.

The existing retention policy is unchanged: ten recent daily SWE/SD dates, then
weekly snapshots back to September 1 of the latest model date's hydrological
year, and ten daily temperature dates. Each project's unreferenced COGs are
cleaned after the existing 48-hour grace period, including legacy orphans within
that project's store. No data is imported from outside that hydrological year.

## Install the updated UI once

Build as described in the [web UI guide](../webui/README.md), then from the
checkout root install it locally or on a mounted site:

```bash
snowcast deploy-ui --dist webui/dist --site-dir site-staging
```

For the remote website, copy only the compiled application, using the same
destination as `deploy` (substitute your SSH destination):

```bash
rsync -rt --protect-args --exclude=data/ --exclude=demo/ --exclude=demo-site/ \
  --exclude=site.json --exclude=.site-config.json --exclude=domains.json \
  webui/dist/ USER@HOST:/var/www/html/v3/
```

Do not add `--delete` over a website containing model data. Normal project
publication does **not** rebuild or copy the UI. Subsequent data publishes need
no UI rebuild. Apache must serve byte ranges for COGs; give `site.json` and all
`catalog.json` files revalidation/no-cache headers. The existing COG host check
still applies. Open `/v3/` to see all selected projects. `?site=URL` selects an
alternate site manifest; `?catalog=URL` still explicitly opens one catalogue.
Only a missing default `site.json` (404) falls back to legacy `data/catalog.json`.
A broken configured manifest never silently switches to a different dataset.

## Map behaviour and scales

- **Dates:** the shared timeline uses UTC calendar days. Each project displays
  its latest output on that exact day, or a visible gap. It never substitutes
  an earlier date. Project status and point values show actual output times.
- **Point history:** clicking chooses the top available project at that point.
  In overlaps, an explicit selector lets you change project. History stays with
  that project when dates change, and share links retain the choice. CSV keeps
  actual source timestamps. Bounding boxes determine candidate domains; nodata
  within a chosen domain remains nodata.
- **Difference:** subtracts the selected dates separately inside each project.
  Projects can have different grids from one another; the two dates within a
  project must align. Missing dates or incompatible grids are reported per
  project and omitted from that difference map.
- **Overview:** all visible domains use the same colour scale. By default this
  spans the configured ranges of the loaded projects. Optional `overview_ranges`
  in the site config pins it, for example `{"swe": [0, 400], "snowdepthavg": [0, 2]}`.
- **Zoomed view:** when only one domain intersects the viewport, or its bounding
  box covers at least 80% of the viewport and contains its centre, its configured
  `display.ranges` becomes the shared map scale. The legend names that project.
  Otherwise the overview scale applies. Overlap priority follows site order.
  Scale ranges stay fixed across dates; difference scales are symmetric.
- **Failures:** a missing/broken project catalogue produces a warning while
  healthy projects remain usable. Retry project catalogues after recovery.
  Raster failures are reported, never replaced with stale dates.

Project ranges belong in each project's manifest, for example TVC might use:

```json
"display": {"ranges": {"swe": [0, 150], "snowdepthavg": [0, 1.5]}}
```

The values above are illustrative; choose ranges appropriate to your model.

Original daily TIFF/ASCII archive synchronization and project-specific download
indexes remain separate operator steps. This stage does not add them or schedule
model runs/publication; see the [project guide](../projects/README.md).

## Synthetic development checks

```bash
python scripts/make_multisite_demo.py
cd webui
npm ci
npx playwright install chromium
npm run test:browser
```

The generated demo has three projects with different grids, ranges and output
times, an overlapping research domain and a missing TVC day. Run `npm run dev`
and open `?site=./demo-site/site.json` to explore it manually. Synthetic data is
labelled and must not be deployed. CI runs the same browser checks, including
Canvas rendering, source point values, gaps, comparisons, sharing, partial
catalogue failures, legacy discovery and mobile layout. Production-size COGs,
real SSH/Apache deployment and GPU rendering still need host/device validation.
