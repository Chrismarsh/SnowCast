# Run and publish a SnowCast website

This is the end-to-end guide for a shared website containing Western Cordillera,
TVC and other independent model projects. Commands below run from the **SnowCast
checkout root** in the Python environment where the runner is installed. The
examples deploy to `/var/www/html/v3-testing/`; use the same destination in your
site config and UI upload command.

- [What each command does](#what-each-command-does)
- [First setup or migration](#first-setup-or-migration)
- [Daily model updates](#daily-model-updates)
- [Build and deploy the UI](#build-and-deploy-the-ui)
- [Local-only preview](#local-only-preview)
- [What to rerun after a change](#what-to-rerun-after-a-change)
- [Where configuration and data live](#where-configuration-and-data-live)
- [Observation datasets](#observation-datasets)
- [Troubleshooting](#troubleshooting)

## What each command does

| Command | Result | When to use it |
| --- | --- | --- |
| `snowcast download-data canswe` | Downloads and verifies the full pinned CanSWE source in the shared local cache | Once per cache/release, or to repair an invalid cache |
| `snowcast site validate SITE_CONFIG` | Validates the site and observation configuration without publishing | Before configuration changes |
| `snowcast site configure SITE_CONFIG` | Applies project selection/order, display settings and observation configuration to local staging | First setup and configuration changes |
| `snowcast site configure SITE_CONFIG --upload` | Applies that configuration to both local staging and the configured webserver | First remote setup and configuration changes |
| `snowcast run PROJECT` | Prepares forcing/configuration, runs or resumes CHM, and postprocesses successful new output | Each model update, for each project |
| `snowcast postprocess PROJECT` | Processes existing CHM output | If postprocessing was skipped or needs to be repeated |
| `snowcast archive PROJECT [--destination ID]` | Copies original TIFF/ASCII products to the project’s configured storage backends | After postprocessing; separate from Web UI publication |
| `snowcast archive PROJECT --dry-run` | Shows changed-file counts without contacting destinations | Before the first archive or a configuration change |
| `snowcast publish SITE_CONFIG --project ID` | Builds local COGs/catalogue, prepares cached observation subsets, uploads the selected project's data and updates the website manifests | After that project's output is ready; uploads by default |
| `snowcast publish SITE_CONFIG --project ID --no-upload` | Prepares the same model and observation data in local staging | Local testing; no SSH/rsync or observation downloads |
| `npm --prefix webui run build` | Compiles the UI into `webui/dist/` | After UI code/dependency changes |
| `snowcast deploy-ui --dist webui/dist --site-dir DIRECTORY` | Installs an already-built UI into a **local or mounted** directory, preserving published data | Local installation; does not upload over SSH |
| `rsync … webui/dist/ USER@HOST:/var/www/html/v3-testing/` | Uploads the compiled UI to the webserver | Initial UI installation and UI updates |

**`publish` does not run `site configure`, download observation sources, or build
or deploy the UI, or upload original archives.** `archive` handles original
TIFF/ASCII storage separately. `run` does not publish or archive. `site configure` does not run CHM or
create observation subsets. Building the UI does not install it on the server.

There is one project-data publishing command. The earlier `site publish`,
`publish PROJECT --site-dir ...`, and `site prepare-canswe` forms are retired.

## First setup or migration

This order also applies when moving from the old committed CanSWE ZIP to the
cached-source workflow. Keep existing project output and your authored settings.

### 1. Install the updated runner and select projects

```bash
python -m pip install -e .
```

Use the updated checkout containing the observation-registry changes. An editable
installation follows that checkout's Python code; rerun installation when package
metadata/dependencies change. A non-editable installation must be reinstalled to
pick up code and packaged registry updates.

For a new site, copy `sites/snowcast.example.json` to `sites/snowcast.json` and edit
it. Keep your existing site config when updating an existing installation.

```json
{
  "version": 1,
  "title": "SnowCast",
  "projects": ["../projects/western-cordillera", "../projects/tvc"],
  "staging": "../site-staging",
  "deploy": {
    "host": "USER@HOST",
    "directory": "/var/www/html/v3-testing"
  }
}
```

Replace `USER@HOST` with your SSH destination/alias. Paths resolve relative to
the **site config file**, not your shell's working directory. Each project entry
is a project folder or its `snowcast.json`. IDs/names come from those manifests;
IDs must be unique. TVC is your own project and is not supplied by the example.
See the [project guide](../projects/README.md) to create/validate model projects.

`staging` must be outside every project's `work/` directory. Later projects in
the list draw above earlier ones where domains overlap. `overview_ranges` can
set the shared overview scale; named projects retain their configured scales.

Omitting `observations` uses the installed registry and default cache. Optional
registry/cache overrides are described [below](#observation-datasets). Set
`"observations": false` for a model-only site.

### 2. Populate the observation cache

```bash
snowcast download-data canswe
```

This downloads and verifies the pinned release, or verifies/reuses a cached copy.
It does not upload observations or alter the website. With custom registry/cache
settings, pass the matching `--registry` and `--cache` options to this command.

### 3. Configure local staging and the remote website

```bash
snowcast site validate sites/snowcast.json
snowcast site configure sites/snowcast.json --upload
```

Configuration can precede the first model publication. Selected projects without
published catalogues are marked unavailable. This is an explicit step: `publish`
checks the installed configuration and fails if it is missing or has changed.

Repeat configuration after changing the selected projects, their order/names,
overview ranges or enabled observation settings. Configure before starting
publishers using the new settings. Old publishers cannot restore removed entries.
Removing a project hides it and retains its files; configuration does not delete
model products or observation histories.

### 4. Publish each project's output and observation contribution

If model output is not yet postprocessed, first complete `snowcast run PROJECT`
(or `snowcast postprocess PROJECT` for existing CHM output). Then:

```bash
snowcast publish sites/snowcast.json --project western-cordillera
snowcast publish sites/snowcast.json --project tvc
```

Publish **each existing project once** when migrating observations. Publishing TVC
only contributes TVC's stations; it does not prepare Western Cordillera's stations.
After both publish, their selections are merged and overlap is deduplicated.
An unpublished project does not block the others.

### 5. Build and deploy the updated UI once

Follow [Build and deploy the UI](#build-and-deploy-the-ui). The old UI requests the
legacy `observations/canswe/index.json`; the new publisher writes a public
`observations.json` pointing to versioned indexes. **Newly published observations
will not appear in the old UI.** Uploading only model/observation data is therefore
insufficient for this migration.

After deployment, reload the page and enable **Map layers → Observations → CanSWE
stations**. Station visibility defaults to off and is remembered by the browser.

## Daily model updates

Once configured, run and publish each project once per update:

```bash
snowcast run projects/western-cordillera &&
snowcast publish sites/snowcast.json --project western-cordillera

snowcast run projects/tvc &&
snowcast publish sites/snowcast.json --project tvc
```

For configured original archives, insert `snowcast archive PROJECT` between
`run` and `publish` for each project. For example:

```bash
snowcast run projects/tvc &&
snowcast archive projects/tvc &&
snowcast publish sites/snowcast.json --project tvc
```

Without archives, that is two `run` commands and two `publish` commands. `&&`
starts publication only when that project's run succeeds. If the outputs are
already postprocessed, use just `publish`. Routine data updates need no
`site configure`, CanSWE download or npm build while their settings/releases and
UI code remain unchanged.

`run` updates forcing metadata when the project uses an archive, prepares a fixed
forcing snapshot, runs/resumes CHM and postprocesses completed output. It indexes
existing met files; supplying the meteorological archive is a separate workflow.
Index-only forcing is externally maintained. A separate `met-update` invocation
is optional for archive-backed projects. `run --no-postprocess` skips postprocessing;
a run that is already up to date also skips new processing.

### Parallel projects and locks

The two `run … && publish …` pairs can run in separate shells or scheduled jobs,
subject to your cluster's resources. Keep each project's run and publish in order.

| Shared resource | Behaviour |
| --- | --- |
| Different project work directories | Model runs can proceed independently |
| The same project work directory | A second active writer fails with `PROJECT is already running`; it does not queue behind the first |
| The same forcing index, explicitly configured by two archive-backed projects | The second metadata writer waits for the first, then reads the updated index |
| CanSWE source cache | Concurrent downloaders wait and reuse the verified source |
| Observation conversion in one site's staging directory | Conversion is serialized; unchanged selections reuse the generated subset |
| Site registration and observation manifest | A lock merges independent project updates so one project does not erase another |

Two projects sharing only an archive do not automatically share an index. Set
both `forcing.archive` and the same explicit `forcing.index` to share incremental
indexing; see [forcing configuration](../projects/README.md#forcing-and-simulation-period).

## Build and deploy the UI

Build from the updated checkout, with its Python environment active. npm's
prebuild step uses the installed runner to refresh the original-download index;
it does not download or convert CanSWE. Node is needed on the build machine, not
the webserver. See the [UI guide](../webui/README.md#build-and-deploy) for prerequisites.

```bash
npm --prefix webui ci
npm --prefix webui run build
```

Then upload the **entire compiled application**, including HTML and hashed assets,
to the same host/directory as the site's `deploy` settings:

```bash
rsync -rt --protect-args \
  --exclude=data/ --exclude=observations/ --exclude=observations.json \
  --exclude=site.json --exclude=.site-config.json --exclude=domains.json \
  --exclude=demo/ --exclude=demo-site/ \
  webui/dist/ USER@HOST:/var/www/html/v3-testing/
```

Replace `USER@HOST`; do not add `--delete` over a site containing published data.
The exclusions protect generated model/observation manifests and assets, including
when an older checkout left stale observations in `webui/public/`. A hard refresh
loads newly deployed HTML/JavaScript; it cannot replace old files still on the
server. Open `https://www.snowcast.ca/v3-testing/` after updating that installation.

For installation on a local/mounted website directory, use instead:

```bash
snowcast deploy-ui --dist webui/dist --site-dir site-staging
```

`deploy-ui` copies the existing build locally and preserves model data, site
configuration and observations. It does not invoke npm and does not read the
site's SSH deployment settings.

Apache must serve byte-range GETs for COGs. Use revalidation/no-cache headers for
HTML, `site.json`, `observations.json` and each model `catalog.json`. Immutable
hashed UI assets, COGs and observation indexes/histories may use long cache times.
The [COG hosting checks](../webui/README.md#hosting-on-an-ordinary-disk) still apply.

Original TIFF/ASCII uploads use `snowcast archive PROJECT`, configured independently
of `site.deploy`. `publish` reads successful archive receipts and uploads only
per-project download indexes alongside the map/observation backend data. See the
[archive guide](../projects/ARCHIVING.md) for HPFX, local and S3-compatible storage.
If a UI build reports that it retained a stale download-index snapshot, preserve
a newer server copy with `--exclude=download-index.json` on the UI rsync command.

## Local-only preview

Use a separate site config, for example `sites/snowcast.local.json`, with the same
projects and `"staging": "../site-preview"`. This keeps the preview apart from your
normal staging directory. It can omit `deploy` or retain it: `--no-upload` never
contacts that destination.

With the observation cache populated and project output postprocessed:

```bash
snowcast site configure sites/snowcast.local.json
snowcast publish sites/snowcast.local.json --project western-cordillera --no-upload
snowcast publish sites/snowcast.local.json --project tvc --no-upload
npm --prefix webui ci
npm --prefix webui run build
snowcast deploy-ui --dist webui/dist --site-dir site-preview
webui/node_modules/.bin/vite preview --outDir site-preview --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080/` on the machine running the server (or forward the port
with SSH for a remote machine). Vite preview serves the already-built site with
byte-range support for COGs; it does not rebuild or publish anything.
`--no-upload` requires the same observation cache as remote publishing. Dependency
installation, explicit `download-data` and npm's download-index refresh may still
use the network; `--no-upload` controls publication, not all preparation commands.

To upload after local testing, configure the normal remote site with `--upload`
and run its `publish` commands without `--no-upload`. Copying the UI alone does
not transfer the preview's model or observation data.

## What to rerun after a change

| Change | Required steps |
| --- | --- |
| New model output, unchanged configuration | `run` then `publish` for that project |
| Existing postprocessed output, publication retry | `publish` for that project |
| Add a project | Add it to the site config; configure locally/remotely; run/postprocess and publish the new project |
| Change site selection/order, project name or overview ranges | Reconfigure; republish affected project data as needed |
| Change observation radius, metadata, enabled datasets or converter version | Reconfigure; publish each selected project that should contribute observations |
| Change the pinned observation release/source | Download with the updated registry; reconfigure; publish each contributing project |
| Missing/corrupt observation cache | `download-data` with the matching registry/cache; retry the affected publication |
| Change frontend code or dependencies | npm build and UI deployment; keep model/observation data intact |
| Upgrade from the old CanSWE ZIP | Complete all steps in [First setup or migration](#first-setup-or-migration), including publication of every project and UI deployment |

A new dataset that uses the existing station format needs a registry entry and a
runner adapter. A new observation renderer also requires a UI update/build.

## Where configuration and data live

| Location | Role | Written by |
| --- | --- | --- |
| `projects/PROJECT/snowcast.json` and referenced CHM settings | Authored model/run configuration | Operator |
| `sites/snowcast.json` | Authored site selection, staging and deployment destination | Operator |
| `snowcast_runner/observations.json` or a configured custom registry | Authored dataset acquisition, conversion and display settings | Operator/developer |
| `PROJECT/work/archive/` | Completed archive receipts used for project download links | `archive`; read by `publish` |
| `~/.cache/snowcast/data/` by default | Full verified observation source shared by projects | `download-data` |
| `PROJECT/work/` | Jobs, forcing snapshots, checkpoints and postprocessed products | Project commands |
| `STAGING/data/PROJECT/` → `WEBSITE/data/PROJECT/` | Model COGs and `catalog.json` | `publish` |
| `STAGING/observations/` → `WEBSITE/observations/` | Subset station histories and immutable indexes | `publish` |
| `STAGING/observations.json` → `WEBSITE/observations.json` | Generated public dataset registry, containing only prepared datasets | `site configure` / `publish` |
| `STAGING/site.json` → `WEBSITE/site.json` | Generated selected-project manifest and availability | `site configure` / `publish` |
| `webui/dist/` → website HTML and `assets/` | Compiled frontend | npm build, then UI deployment |

The authored and public observation files share a name but have different jobs.
**Edit the authored registry, never the generated website manifests.** Local cache
paths, source-acquisition settings and SSH credentials are not included in the
public observation registry. Only registry/code/test fixtures belong in Git;
full sources and generated observation assets remain outside version control.
The old checkout-level `runs/` directory is unused by the current project runner.

Each project retains ten recent daily SWE/SD dates plus older weekly snapshots
back to September 1 of the latest model date's hydrological year; temperature
retains ten daily dates. The per-store 48-hour COG orphan grace period is unchanged.
Daily original archives remain daily. Old immutable observation assets are retained
for open pages; there is currently no automatic observation garbage collection.

## Observation datasets

The installed [registry](../snowcast_runner/observations.json) defines dataset IDs,
labels, descriptions, enabled status, pinned URLs/releases/checksums, adapters,
renderers, variables/units, attribution and station-selection radius.

### Cache and custom registry

Cache precedence is `--cache` for `download-data` / `observations.cache` for a site,
then `SNOWCAST_DATA_CACHE`, then `$XDG_CACHE_HOME/snowcast/data`, falling back to
`~/.cache/snowcast/data`. A site's cache setting does not automatically apply to
the standalone download command: use matching options or the shared environment
variable. Releases and checksums have separate cache locations.

To use operator-owned settings, copy the registry to `sites/observations.json`
and add this field to your site config:

```json
{
  "observations": {
    "registry": "./observations.json",
    "cache": "/shared/snowcast-data"
  }
}
```

The snippet shows fields to merge into the full site config. Populate that cache:

```bash
snowcast download-data canswe --registry sites/observations.json --cache /shared/snowcast-data
```

On a machine without Internet access, import an existing pinned NetCDF using
`--source /path/to/CanSWE-CanEEN_1928-2025_v8.nc` with the same options. Downloads
are streamed, checksum-verified and installed atomically. Interrupted or invalid
transfers cannot replace a valid source. Routine publication never changes the
pinned release or downloads a missing source implicitly.

### Subsetting and publication

Publication selects stations using the selected project's **published WGS84
catalogue bounds**, plus the configured nearby radius (CanSWE defaults to 100 km).
This is geographic bounding-rectangle selection, not exact mesh-mask clipping.
Stations outside every loaded model domain show **observations only**.

Conversion is reused while the source release, converter version, project bounds,
metadata and selection settings are unchanged; daily model timestamps do not
trigger regeneration. Each project has its own contribution. The website merges
and deduplicates contributions under a lock, excluding removed projects/datasets.
A domain with no stations is a valid empty contribution. Only prepared datasets
appear in the generated public registry; configured-but-unpublished projects do
not prevent other projects from publishing.

Histories are uploaded and verified before immutable indexes are written. The
public registry switches last. The UI reads that registry at runtime, then fetches
the selected dataset's station index and clicked histories. No observation ZIP,
npm rebuild or Git commit is involved in routine data updates.

Missing/corrupt sources and conversion failures can leave the model publication
complete but observations incomplete. The command reports the failure, gives the
matching download command for a cache problem, and exits nonzero. With unchanged
configuration, the previous valid observation contribution remains available;
other successfully prepared datasets can still publish. Retry after repairing the
problem. An interrupted upload leaves the last public observation manifest intact.

Adapters for additional snow-station datasets must emit `snow-stations-v1`:
source metadata, station locations with immutable history URLs, dated tuples
`[date, swe_mm, depth_m, agency_swe, agency_depth, qc_swe, qc_depth]`, and 24
half-month seasonal bins. Normalize units, missing values and flags to this common
contract. See [CanSWE processing](../webui/data/README.md) for its scientific rules.

## Troubleshooting

| Symptom | Check and remedy |
| --- | --- |
| `Site is not configured` or `Site configuration changed` | Run `site configure SITE_CONFIG --upload` for remote publication, or omit `--upload` for local-only use. Publishing does not configure automatically. |
| `no valid cached source` | Run the exact `download-data` command in the error. Check that download and publication use the same registry, cache path and OS user. |
| Model dates update but CanSWE still lacks TVC | Check the new observation index and deployed JavaScript as described below. Build and deploy the updated UI if it still requests the legacy index. |
| Stations from only one project appear | Publish each other project once. Configuration alone does not generate its observation contribution. |
| No observation dataset is listed | Inspect `observations.json` and publication errors. The dataset may be disabled, unprepared or missing its cached source. |
| Dataset is listed but no markers appear | Enable its station toggle in Map layers; check the selected dataset, search/filter and map extent. Nearby stations may lie outside the model footprint. |
| Local preview works but the remote site does not change | `--no-upload` writes only staging, and `deploy-ui` is local/mounted only. Use remote configuration/publication and the separate UI rsync. |
| `PROJECT is already running` | Wait for that project's active run/publish to finish, then retry. Different projects can proceed independently. |

### Trace missing TVC stations

1. Open the website's `observations.json`, for example
   <https://www.snowcast.ca/v3-testing/observations.json>.
2. Find the CanSWE dataset and follow its `index` relative to the website root.
   The current format is `observations/canswe/index-<hash>.json`. Inspect its
   `domains`, `nearby_km` and station names. Do not use the old fixed `index.json`
   as evidence about the new publication.
3. With CanSWE v8, the TVC footprint used by this deployment and a 100 km radius,
   the nearby selection contains **Caribou Creek, Inuvik UA, Satah River and Sunny
   Lake**. They lie outside the model domain and have observations-only panels.
   A different domain or radius can change the selection.
4. In browser Developer Tools → Network, reload with caching disabled and enable
   the station layer. The updated UI requests `observations.json` followed by the
   versioned index. Requests only to `observations/canswe/index.json` identify the
   old UI. Rebuild and upload the complete `webui/dist/`, then reload.
5. If the versioned index has no TVC contribution, rerun TVC publication and read
   its exit status/output. If it contains only TVC, publish Western Cordillera too.

Old files may safely remain on the server for old pages. Deleting the legacy index
is not a migration step; the updated frontend must load the new manifest.

The viewer normally discovers models through `./site.json`. `?site=URL` selects
an alternate model manifest and `?catalog=URL` selects one catalogue explicitly;
the observation registry still comes from beside the deployed UI's `index.html`.
Only a missing default model `site.json` (HTTP 404) falls back to legacy
`data/catalog.json`. A malformed configured manifest reports an error.
