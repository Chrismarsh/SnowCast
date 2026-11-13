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
website root, such as `/var/www/html/v3-testing`. No username is built into the runner.
For a local or mounted website, omit `deploy` and use `publish --no-upload`. Only project IDs, display names,
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

For each routine update, run and publish each project once:

```bash
snowcast run projects/western-cordillera &&
snowcast publish sites/snowcast.json --project western-cordillera

snowcast run projects/tvc &&
snowcast publish sites/snowcast.json --project tvc
```

`run` refreshes the forcing index, prepares the configuration, runs/resumes CHM
and postprocesses successful new output. The `&&` publishes only after that
project's run succeeds. If you already ran `postprocess`, use just `publish`.
Each project can update independently; the other keeps its existing catalogue.

**`publish` uploads by default** to `deploy.host` / `deploy.directory` in the site
configuration. It generates COGs in staging, uploads that project's catalogue
and assets, and updates the remote website registry. Missing deployment settings
fail before conversion with instructions to configure them or use `--no-upload`.

For **local-only testing**, configure staging once without `--upload`, then:

```bash
snowcast site configure sites/snowcast.json
snowcast publish sites/snowcast.json --project tvc --no-upload
```

`--no-upload` generates the same COGs and updates the local site registry, with
no SSH or rsync calls, even if the config contains a remote deployment destination.
It never changes the remote website. Repeating either publication mode is safe.

There is one public publishing command. The old `snowcast site publish ... --upload`
and `snowcast publish PROJECT --site-dir DIR` forms have been removed; update any
scripts to `snowcast publish SITE_CONFIG --project ID [--no-upload]`.

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
  --exclude=observations/ --exclude=observations.json \
  webui/dist/ USER@HOST:/var/www/html/v3-testing/
```

Do not add `--delete` over a website containing model data. Normal project
publication does **not** rebuild or copy the UI. Subsequent data publishes need
no UI rebuild. Apache must serve byte ranges for COGs; give `site.json` and all
`catalog.json` files revalidation/no-cache headers. The existing COG host check
still applies. Open `/v3-testing/` to see all selected projects. `?site=URL` selects an
alternate site manifest; `?catalog=URL` still explicitly opens one catalogue.
Only a missing default `site.json` (404) falls back to legacy `data/catalog.json`.
A broken configured manifest never silently switches to a different dataset.

## Observation datasets

The one maintained registry is [`snowcast_runner/observations.json`](../snowcast_runner/observations.json).
It is included in the installed wheel. It lists dataset IDs, labels, descriptions,
enabled status, pinned source releases/URLs/checksums, conversion adapters,
renderers, variables/units, attribution, and the station selection radius.
No downloaded source or generated station data is tracked in Git.

Download the full source **once** into a shared local cache:

```bash
snowcast download-data canswe
snowcast publish sites/snowcast.json --project tvc
```

`download-data` verifies and reuses an existing source. Concurrent downloaders
wait on the same cache lock. Downloads are streamed to a temporary file, verified,
and atomically installed. Interrupted/invalid transfers cannot replace valid data.
The cache defaults to `$XDG_CACHE_HOME/snowcast/data` (normally
`~/.cache/snowcast/data`). Set `SNOWCAST_DATA_CACHE` or use `--cache /path/to/cache`
to share a cache across project folders. Releases remain pinned until the registry
is explicitly changed. To import a download on a machine without Internet access:

```bash
snowcast download-data canswe --source /path/to/CanSWE-CanEEN_1928-2025_v8.nc
```

`publish` **never downloads observation sources**. It verifies the cache, selects
stations using this project's published WGS84 bounds plus the registry's default
100 km nearby radius, and uploads compressed histories before the indexes and
public manifest. `--no-upload` prepares the same data locally with no SSH/rsync or
observation download. Stations outside model coverage show observations only.
Selection uses geographic bounding rectangles, not exact mesh masks.

Conversion is reused while source release, converter version, project bounds,
metadata and selection settings remain unchanged. Daily model dates do not cause
conversion. Each project's contribution is stored separately; the website merges
and deduplicates the configured projects under its site lock. Unpublished projects
do not block publication. A domain with no stations produces an empty contribution.

The generated public `observations.json` lists only successfully prepared datasets
and their immutable station-index URLs. The UI reads it at runtime, builds the
dataset selector and loads station histories on demand. Source acquisition settings
and local paths stay private. UI installation preserves this manifest and the
`observations/` directory. There is **no ZIP, npm rebuild, Git commit or assistant
step** for routine observation publication.

For custom settings, copy the registry to an operator-owned file and use:

```json
"observations": {
  "registry": "./observations.json",
  "cache": "/shared/snowcast-data"
}
```

These paths are relative to the site config. Download with matching options:
`snowcast download-data canswe --registry sites/observations.json --cache /shared/snowcast-data`.
Omit `observations` to use the installed registry/environment cache; set it to
`false` for a model-only site. Set a dataset's `enabled` to `false` to hide it.
After changing the registry or selected projects, run `site configure` again
(with `--upload` for the host), then publish affected projects. Old publishers
cannot restore removed projects/datasets. Existing immutable data files are retained
for open browser pages; no automatic observation garbage collection is performed.

If a source is missing/corrupt or conversion fails, model publication can complete,
the last valid observation contribution is retained, and the command exits nonzero
with the failing dataset and exact `download-data` command. Other valid datasets
can still publish. Retry the same publish after repairing the cache. An interrupted
upload leaves the last public observation manifest intact.

To add another station dataset, add a registry entry and an adapter producing
`snow-stations-v1`: a station index with source metadata and immutable history
URLs, dated tuples `[date, swe_mm, depth_m, agency_swe, agency_depth, qc_swe, qc_depth]`,
and the same 24 half-month seasonal bins. Adapters must normalize units, missing
values and flags to the common contract. Other observation types require a new
renderer. The UI has no dataset IDs, download URLs or release dates hard-coded.

### Migrate from the old bundle

1. Install the updated runner (`python -m pip install -e .` from the checkout).
2. Run `snowcast download-data canswe` (or import the existing NetCDF).
3. Run `snowcast site configure sites/snowcast.json --upload`.
4. Publish each existing project once to populate its observation contribution.
5. Build/deploy the updated UI once using the observation exclusions above.

The removed `site prepare-canswe` command and build-time ZIP extraction are replaced
by this workflow. Old observations can remain on the server; the new registry
references only the newly published immutable indexes.
