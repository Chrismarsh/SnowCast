# SnowCast projects

SnowCast is an installable runner. A project defines independent CHM domains;
the shared code checkout does not hold their generated configuration or state.
The first project example is [western/snowcast.json](western/snowcast.json).
It preserves the current western model's inputs, start date, output variables,
800-rank allocations and AEP exports, but uses a new `runs/western-cordillera/`
workspace. It does not automatically copy or adopt the production checkpoints.

## Install and validate

Install into your existing CHM/Spack Python environment:

```bash
python -m pip install -e .
snowcast validate projects/western --config-only
snowcast validate projects/western
```

`--config-only` checks configuration structure without requiring meshes or
forcing. Full validation checks input paths, CRS, CHM mesh references and MPI
partition counts. Neither command submits jobs or creates a workspace.
CHM, `chm_ugrid2grid`, MPI and PBS remain externally installed executables.
The project can live outside this repository; all paths are relative to its
`snowcast.json`, never the caller's working directory. Executable names without
a slash resolve through PATH inside the job environment. Commands are argument
arrays, not shell strings; a job's explicit `setup` file supplies shell setup.

The old `python snowcast.py -c config_hrdps_west.py` workflow remains available.
Both runners use the same incremental met updater and index lock. The legacy
plot/upload stages are not invoked by the project runner. Do not schedule both
workflows against the same mutable checkpoints or model outputs.

## Project definition

The manifest has `version: 1`, an `id`, a `work_root`, optional `defaults`, and
a list of `domains`. Each domain has an `id` and optional `name`, `model`,
`forcing`, `postprocess`, and `display`. Nested objects inherit defaults;
lists replace defaults. Unknown keys are rejected so spelling mistakes cannot
silently select a default path or grid. IDs are lowercase letters, digits,
hyphens or underscores, starting with a letter. IDs must be unique in a project.

Each domain gets `work_root/<domain-id>/`. A workspace ownership marker prevents
different project IDs from claiming the same work root. Projects can share
read-only meshes and forcing outside that root. A project ID must remain stable
and be unique among projects publishing to the same site.

| Section | Settings |
| --- | --- |
| `model` | `config` (JSON/JSON5 CHM template), optional `start_date`, `command` (default `["CHM", "-f", "{config}"]`), `output_file` (default `output.nc`), `max_runs` (10), `checkpoint_keep_days` (3), `no_data_codes` (empty), `assets`, `job` |
| `forcing` | `index`: path to the CHM forcing metadata JSON; optional `archive`: directory of NetCDF forcing files to index |
| `postprocess` | `variables`, `source_resolution` (degrees), `method`, `recent_steps`, `exporter`, optional UGRID topology `mesh`, `grid`, `ascii`, `job` |
| `grid` | `crs`, `[dx, dy]` `resolution` in target CRS units, optional `[west, south, east, north]` `bounds`, `resampling` (`nearest`, `bilinear`, `average`) |
| `ascii` | `enabled` (false), `variables` (`swe`, `t`), `resolution` (0.036 degrees); exports latest selected timestamp in EPSG:4326 |
| `display` | `ranges`, mapping `swe`, `snowdepthavg`, or `t` to `[minimum, maximum]`; published in the domain catalogue |

The initial adapter supports SWE, snow depth and temperature. Domain names and
locations are arbitrary; additional variables or model engines require an
adapter change. CHM physics remain in the CHM template. Its mesh paths resolve
relative to that template. Use absolute references for additional CHM input
paths or map workspace filenames/directories to input paths with `model.assets`.
Assets are symlinked as inputs; output, config and log names are reserved.

Forcing uses the existing CHM metadata JSON, which lists the files and their
time ranges. Supply `archive` to have SnowCast maintain it incrementally using
the shared updater in `met/main.py`. The western example accepts your existing
`met/hrdps` directory or symlink:

```json
"forcing": {
  "archive": "../../met/hrdps",
  "index": "../../met/metdata-hrdps.json"
}
```

You can instead set `archive` directly to an external location such as
`/path/to/hrdps`; there is no need to create a repository symlink yourself.
`prepare` creates `work_root/<domain>/met/archive` as a symlink to the resolved
archive, creates or updates the shared metadata JSON, and writes a separate
`met/index.json` snapshot for CHM. Repeated preparation reuses the correct link;
an existing directory or link to another archive is rejected rather than
overwritten. The NetCDF files remain in their original archive.

The updater lists `*.nc` in the archive and opens only files absent from the
existing index. It reads their actual time coordinates, including late-arriving
files with dates before the current latest entry, then orders records by start
time. Existing metadata is retained; an unchanged index is not rewritten and
previously indexed NetCDF files are not reopened. Files already indexed are
assumed complete; changes to those files' time ranges require correcting their
metadata explicitly. Downloads and production of the NetCDF files remain the
responsibility of the upstream meteorology workflow.

Updates lock the canonical index path and replace the JSON atomically. Domains
sharing an archive should use the same `index`, so concurrent invocations and the
legacy runner serialize updates even through symlink aliases. The lock lives
beside the index, so the archive itself can be read-only. Index storage must be
writable. A missing archive, empty initial archive or unreadable new NetCDF
fails the stage without replacing the previous index. No archive files or old
metadata entries are deleted. Separate forcing archives must have separate
indexes; a project assigning different archives to the same index is rejected.

The JSON remains the standard CHM list of `start_time`, `end_time`
(`YYYYMMDDTHHMMSS`, UTC) and `file_name`. Relative filenames resolve against the
source index. Each preparation takes a workspace snapshot with absolute paths,
preserving timestamps and additional metadata. A later shared index update
does not change a submitted job's snapshot. The metadata's latest end time
determines whether CHM is up to date.

Omit `archive` (or override an inherited archive with `null`) to consume an
externally maintained index without scanning directories or reading NetCDFs.
In that mode the index must already exist. With `archive` configured, validation
allows a missing index so the first preparation can create it. `validate` itself
does not create links, update metadata or submit jobs.

`job` applies independently to CHM and regridding. Defaults run locally with one
rank. PBS projects specify `mode: "pbs"`, `nodes`, `cpus_per_node`,
`ranks_per_node`, `ranks`, `memory`, `walltime`, `queue`, `launcher`, and optionally
`setup`, `qsub`, `qstat`, and `poll_seconds`. The launcher may use `{ranks}`.
Ranks must agree with the allocation and partitioned mesh/checkpoints.
Local jobs can use `timeout_seconds`; PBS jobs use their walltime and export it
as `CHM_WALLCLOCK_LIMIT` for checkpointing.

Failures stop subsequent stages and are recorded in `status.json`. Retries are
opt-in through `attempts`, `retry_codes`, and `retry_delay_seconds`; the default
is one attempt. `model.no_data_codes` maps explicit nonzero model/wrapper exits
to `up_to_date`, skipping postprocessing. A latest checkpoint at or beyond the
forcing end also produces `up_to_date`. Successful CHM completion requires its
`clean_exit` marker. Exit zero without that marker continues only when a
checkpoint was created or updated, up to `max_runs`; no checkpoint progress is
an immediate failure. Optional project-level
`"notifications": {"webhook_env": "SNOWCAST_WEBHOOK_URL"}` sends failure messages
to an HTTPS JSON webhook (Slack-compatible `text` payload). Its URL is read from
the runner environment; notification errors never replace the original failure.
Notifications are disabled by default. Downloading meteorology remains outside
this adapter; incremental metadata updates are included when an archive is configured.

## Prepare, run, and inspect

```bash
snowcast prepare projects/western --domain western-cordillera
snowcast met-update projects/western --domain western-cordillera
snowcast run projects/western --domain western-cordillera
snowcast status projects/western
snowcast postprocess projects/western --domain western-cordillera
```

`prepare` creates the workspace, archive link, resolved CHM configuration and
forcing snapshot without submitting a job. It refreshes metadata when an archive
is configured. `met-update` performs just the link setup and shared metadata
update; it leaves any existing CHM configuration and forcing snapshot untouched,
and does not require model input files. It requires `forcing.archive`.

`run` prepares the domain, including the same incremental metadata refresh,
then executes CHM followed by postprocessing. A separate met-update cron is
optional; `--no-postprocess` runs the preparation and CHM stages only. The CHM
template is never modified. A domain must
be selected when a project has more than one. Use independent cron invocations
for each domain. One domain's missing inputs or job failure does not block
another domain's invocation.

The workspace contains `chm/config.json`, `chm/output/` (including checkpoints),
`met/archive` (when configured), `met/index.json`, `jobs/`, `postprocess/`, and
`status.json`. There is no shared
process-wide `chdir`. A process lock excludes duplicate domain runs and remains
held by a local job if its parent runner is killed. PBS submissions are recorded
before submission and recovered before changing any inputs or staging files.

If acknowledgement is lost during `qsub`, the runner deliberately refuses to
submit another job. Inspect the scheduler and the `jobs/*.pending.json` command
and result path. Once the actual job ID is known, set `state` to `submitted` and
`job_id` to that ID in the pending file, then retry. Clear a pending file only
after confirming its job is no longer running. A failed `qstat` without a job
result retains the pending file; a scheduler outage never counts as success.

## Postprocessing and grid stability

The adapter invokes the documented `chm_ugrid2grid` flags: `--dxdy`, `--method`,
`--timeoffset`, `--tiff-output`, `--overwrite`, `--variables`, and optional
`--mesh`. That executable currently exports geographic rasters; it has no
target-CRS flag. SnowCast performs an explicit blockwise raster conversion when
the project's output grid differs. Reprojecting a geographic intermediate adds
a resampling step; it is not direct conservative mesh-to-projected-grid export.

With no explicit bounds, the first complete export establishes the target grid
in `postprocess/grid.json`. A source already matching the requested CRS and
nominal spacing retains its exact transform (including the small live western
spacing deviation). Later dates must have the same source grid. Configured
bounds must span whole cells. A changed grid requires a new workspace and a
rebuilt history; it cannot silently shift existing dates.

All requested variable/timestamp combinations are validated before current
outputs are rotated. TIFFs preserve source Float32/Float64 precision, masks,
nodata and scale/offset; Float32 conversion is confined to COG publication.
Integer rasters are promoted to Float64 to represent NaN nodata. Reprojection
merges explicit masks and nodata before
interpolation. ASCII contains physical values with `-9999` nodata. Current and
archived TIFFs, ASCII grids and companion files remain within the domain.
Checkpoint retention is independent of the September-based published history;
the runner does not reset the physical model on September 1.

## Publishing and the website boundary

Data publication and application deployment are explicit commands:

```bash
snowcast publish projects/western --domain western-cordillera --site-dir /path/to/site
npm --prefix webui ci
npm --prefix webui run build
snowcast deploy-ui --dist webui/dist --site-dir /path/to/site
```

These site commands operate on a **local or mounted POSIX filesystem**. They do
not transfer project data to a remote web server over SSH. The existing legacy
uploader is unchanged; remote multi-project site publishing is a follow-up.

Publication writes `data/<project-id>/<domain-id>/catalog.json` and COGs. It
applies ten recent daily dates plus older weekly snow snapshots within the
current September–August hydrological year and the existing 48-hour cleanup
grace period. A short site lock merges a successful domain into `domains.json`,
preserving concurrent publications. The registry lists only successfully
published catalogues. Asset IDs include project/domain identity. No UI files
are written by `publish`.

`deploy-ui` installs built assets before HTML entrypoints, preserves old assets
for open pages, and leaves `data/`, the domain registry and an existing download
index intact. The UI stays in this repository and has an independent build.

**The current viewer still opens one catalogue at a time.** A published domain
can already be inspected with, for example,
`?catalog=./data/snowcast/western-cordillera/catalog.json`. Reading `domains.json`
to show domains simultaneously, automatic colour-range switching, domain-aware
downloads/observations, and remote site registration remain later UI/publishing
work. This branch supplies their metadata contract and the runner foundation.

## Manual western migration check

1. Keep the existing cron unchanged while validating the new project. Check the
   template, mesh/parameter references, forcing archive/index and `environment.sh`
   on the actual cluster. The sample's 2025-09-01 start date mirrors the existing config.
2. Run `validate`, then `prepare`; inspect the archive symlink, shared metadata,
   generated configuration and snapshot paths. With an existing metadata index,
   preparation reads time coordinates only for previously unindexed files.
3. With the old model writer stopped, **copy** compatible checkpoints into the
   new domain's `chm/output/checkpoint/`. Do not point both runners at one writable
   checkpoint directory. Verify rank count and CHM version compatibility.
4. Manually run one domain invocation. Check PBS resources, continuation,
   `clean_exit`, output timestamps, masks, scale/offset and AEP grids. Small fake
   executables test the workflow in CI; real CHM/MPI/PBS runs still need this check.
5. Publish to a separate staging site and inspect it through `?catalog=...`.
   The new storage namespace can duplicate existing live COGs, so check disk
   usage before a full backfill. Changing the production cron or deployment
   target is a separate operator action.
