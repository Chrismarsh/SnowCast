# Independent SnowCast projects

One project is one independently configured CHM domain/run. Its folder owns its
configuration, generated jobs, forcing metadata, checkpoints, outputs and
processed products. The installed `snowcast_runner` package owns the reusable
implementation. Projects do not depend on the SnowCast checkout or on one another.

A separate [site configuration](../sites/README.md) selects projects for a shared
website, with independent publication and simultaneous multi-project maps. For
the complete daily command sequence, observation cache and separate UI deployment,
use the [site workflow](../sites/README.md).

## Install and start a project

Install into your existing CHM/Spack Python environment **from the repository root,
where `pyproject.toml` is located**:

```bash
cd /path/to/SnowCast
python -m pip install -e .
snowcast validate projects/western-cordillera --config-only
```

For an installation that does not depend on keeping the checkout, use
`python -m pip install /path/to/SnowCast` instead. CHM, `chm_ugrid2grid`, MPI and
PBS remain externally installed executables.

Copy [western-cordillera](western-cordillera/) to your project location. The
example retains the Western model's physics, 800-rank allocations, output
variables, AEP exports and September 1, 2026 start date. Before using it, set:

- `forcing.archive` in `snowcast.json` to the full met archive path.
- `meshes.mesh` in `chm/western.json` to the actual partition file.
- `environment.sh` if your Spack environment is outside the repository root.
  It sources `~/.profile`, then activates the root found two directories above
  that script, regardless of the batch job's working directory. For a project
  copied outside the checkout, set `SNOWCAST_SPACK_ENV` in this script or in
  `~/.profile` to the actual Spack environment path. Both model and postprocessing
  jobs source this file, including fresh PBS shells.
- The model and postprocessing PBS allocations for your cluster.

The mesh and forcing paths are explicit placeholders; the environment setup
defaults to the repository's Spack environment. Preparation does not adopt existing
checkpoints. All authored configuration lives in the project folder or
explicitly referenced input locations.

```bash
snowcast validate /projects/western-cordillera
snowcast prepare /projects/western-cordillera
snowcast run /projects/western-cordillera
snowcast status /projects/western-cordillera
```

`validate --config-only` checks the manifest without requiring model inputs.
Full validation also resolves CHM overrides and checks input paths, grid CRS
and mesh partition ranks. Validation does not create state or submit jobs.
`prepare` creates the resolved configuration and forcing snapshot without
submitting a new job. All commands accept a directory or its `snowcast.json`.
There is no `--domain` argument.

## Manifest and file ownership

Version 2 is flat. A minimal project is:

```json
{
  "version": 2,
  "id": "western-cordillera",
  "name": "Western Cordillera",
  "model": {
    "config": "chm/base.json",
    "overrides": "chm/western.json",
    "start_date": "2026-09-01"
  },
  "forcing": {"archive": "/absolute/path/to/hrdps"}
}
```

`id` is stable, starts with a lowercase letter, and contains lowercase letters,
digits, hyphens or underscores. Use distinct IDs for projects you intend to
publish together. `name` is an optional display label. Unknown settings are
rejected. `defaults`, `domains`, and `work_root` no longer exist.

| Path within the project | Owner and purpose |
| --- | --- |
| `snowcast.json`, `chm/`, `environment.sh` | Authored project settings; never rewritten by preparation |
| `work/met/metadata.json` | Incremental metadata when an archive is configured without an explicit index |
| `work/met/index.json` | Fixed metadata snapshot supplied to CHM |
| `work/met/archive` | Convenience link to the configured archive |
| `work/chm/config.json` | Resolved CHM configuration |
| `work/chm/<mesh inputs>` | Symlinks to the configured mesh/partition and its referenced inputs |
| `work/chm/output/` | Model output, `clean_exit`, and `checkpoint/` |
| `work/jobs/` | Generated scripts, execution logs, exit results and pending PBS submissions |
| `work/jobs/<project>-chm-chain-*/` | Frozen backfill request and per-segment PBS scripts, logs and outcomes |
| `work/postprocess/` | Grid definition, current and archived TIFF/ASCII products, export staging |
| `work/status.json` | Last recorded stage/state and failure details |

Place the project folder itself on the desired filesystem; `work/` cannot be
redirected with a symlink. Read-only inputs can be shared through absolute paths.
Paths in the manifest resolve relative to `snowcast.json`, independent of the
caller's working directory. Executable names without a slash resolve through
PATH inside the job environment. Commands use argument arrays, not shell strings.

| Section | Settings |
| --- | --- |
| `model` | `config`, optional `overrides`, `remove`, `start_date`, `command`, `output_file`, `max_runs`, `checkpoint_keep_days`, `no_data_codes`, `assets`, `job` |
| `forcing` | `archive` and/or `index` |
| `postprocess` | `variables`, `source_resolution`, `method`, `recent_steps`, `exporter`, optional topology `mesh`, `grid`, `ascii`, `job` |
| `grid` | `crs`, `[dx, dy]` `resolution`, optional `[west, south, east, north]` `bounds`, `resampling` |
| `ascii` | `enabled` (false), `variables` (`swe`, `t`), `resolution` (0.036 degrees) |
| `display` | Suggested `ranges` for `swe`, `snowdepthavg`, and `t` |
| `notifications` | Optional `webhook_env` environment-variable name |

## CHM base configuration and overrides

`model.config` is a JSON/JSON5 CHM configuration. `model.overrides` optionally
names a JSON/JSON5 fragment. A project may use its own complete configuration
without overrides, or explicitly reference a shared base outside its folder.
There is no implicit inheritance between projects.

Objects merge recursively; scalars and entire lists replace their base values.
For example, an override can select another mesh and replace the modules:

```json
{
  "meshes": {"mesh": "/absolute/path/to/tvc.np40.partition"},
  "modules": ["solar", "iswr_from_obs", "FSM"],
  "config": {"FSM": {"example_option": "example_value"}}
}
```

The module list and option above are illustrative, not a validated TVC physics
configuration. Replacing `modules` does not implicitly delete module settings or
CHM's `remove_depency` entries. To remove inherited object keys, put explicit
JSON pointers in the project's model settings, for example:

```json
{"remove": ["/config/snow_slide", "/remove_depency/snow_slide"]}
```

Removal happens after merging; a missing key is an error. Escape `/` as `~1`
and `~` as `~0` in a pointer. Remove object keys this way; replace whole lists
rather than editing list elements by index. `null` is a value, not a deletion.

For a serial CHM run, use the unpartitioned mesh and parameter files:

```json
{
  "meshes": {
    "mesh": "/absolute/path/to/FABDEM_tvc_50x50.mesh",
    "parameters": {"file": "/absolute/path/to/FABDEM_tvc_50x50.param"}
  }
}
```

Set the project's `model.job.ranks` to `1` and `model.job.launcher` to `[]`
to invoke CHM directly. PBS can still allocate this serial job. Parameter and
initial-condition entries may be named objects or lists of filenames; preparation
preserves that structure and writes staged basenames at each file entry (for
example, `meshes.parameters.file` becomes `FABDEM_tvc_50x50.param`).

Mesh paths resolve relative to the configuration file that declares each mesh
or parameter/initial-condition file entry. An override can therefore replace an
absent base input before validation. Inherited entries retain their base origin
even when another entry in the same object is overridden.
Errors identify the project, key, source configuration, resolved path and rank
mismatch where relevant.

`prepare` symlinks these inputs into `work/chm/`, where CHM runs. The generated
configuration's `meshes` entries use just the staged filenames, relative to
that directory. For a `.partition`, it also links the mesh and parameter files
named inside it, preserving their relative layout. The usual
`<name>.partition.meshes/` directory
is linked as a whole; large mesh files are neither copied nor rewritten.
Relative entries are resolved from beside the source partition and must stay
below that directory (no `..`); absolute entries are validated and left as-is.
Partition metadata ranks and all referenced mesh/parameter files are checked
by full validation and preparation. Repeating preparation reuses matching
links; conflicting names or existing files produce an error before staging.
No additional `model.assets` entries are needed for these partition inputs.

Other module-specific file inputs should use absolute
paths or explicit `model.assets` aliases, which create read-only input references
in the execution directory. Arbitrary CHM strings are not guessed to be paths.

After resolution, SnowCast supplies `forcing.file`, `output.output_dir` (the
basename `output`, resolved by CHM from its `work/chm/` working directory), the
requested output variables, and `option.startdate` when `model.start_date` is
set. Authored files remain unchanged. CHM settings not managed by the runner,
including physics and checkpoint options, remain under project control.

## Forcing and simulation period

With `forcing.archive`, `prepare` and `run` incrementally index that directory.
Only unindexed NetCDF files are opened, including late arrivals. The configured
archive is read directly; an existing directory symlink is supported. The
archive may be read-only. Downloading or producing NetCDFs stays with the
upstream meteorology workflow.

`model.start_date` is inclusive. Daily files named `YYYYMMDD.nc` or
`YYYY-MM-DD.nc` before that date are skipped before path resolution, stat or
NetCDF reads. Other names require reading their time coordinates. Directory
entries must still be listed to discover files.

Existing metadata remains authoritative. The CHM snapshot excludes intervals
ending before the start date before checking file availability. Intervals that
cross the cutoff remain available. Older cached metadata is retained for other
consumers; source files are never removed. Moving the start date earlier allows
the next update to index newly relevant days. Without a start date, indexing is
unrestricted.

To update metadata alone:

```bash
snowcast met-update /projects/western-cordillera
```

This does not require model input files and leaves an existing CHM snapshot
unchanged. A separate met-update cron is optional because `run` also updates
metadata. No eligible forcing is an error before model submission.

To consume an externally maintained CHM JSON file, configure only `index`:

```json
{"forcing": {"index": "/absolute/path/to/metdata-hrdps.json"}}
```

That mode neither scans archives nor opens NetCDFs. Standard CHM records contain
`start_time`, `end_time` (`YYYYMMDDTHHMMSS`, UTC), and `file_name`. Relative file
names resolve against the metadata JSON; additional fields and record order
are preserved in the snapshot.

To share incremental indexing between projects, configure both `archive` and
an explicit `index`. Writers lock the canonical index path, including symlink
aliases used by different projects. A small archive-binding file next to the index
prevents two independent projects from updating one index from different
archives. Different start dates filter independent snapshots without removing
shared history. Use separate indexes for separate archives.

If you relocate the same forcing archive and keep the old directory as a symlink
to its new location, existing metadata file paths remain valid. The runner
resolves both the recorded archive path and the configured path before comparing
them. A successful update refreshes the archive binding to the new canonical
path; a failed update preserves the previous binding and metadata. You can keep
`forcing.archive` pointing through the old symlink or update it to the new path.
Keep the old symlink while existing metadata or submitted jobs still reference
it. The paths must also be accessible on the compute nodes.

After pulling the relocation fix into the installation used by cron, check each
project without submitting CHM:

```bash
snowcast met-update projects/western-cordillera
snowcast met-update projects/tvc
```

This preserves existing metadata and indexes any new forcing files. An unchanged
metadata index can still contain the old path; that is valid through the symlink.
If the old path no longer resolves to the same archive, the runner rejects the
mismatch and reports both paths. A genuinely different forcing archive needs a
separate index; do not remove its binding simply to bypass that check.

Index writes are atomic. An unchanged index is not rewritten, and an unreadable
new file leaves the previous index intact. Already indexed files are assumed
complete; changed time ranges require explicitly correcting their metadata.

## Execution, checkpoints and errors

Model and postprocessing `job` settings are independent. Defaults run locally
with one rank. PBS settings include `mode`, `nodes`, `cpus_per_node`,
`ranks_per_node`, `ranks`, `memory`, `walltime`, `queue`, `launcher`, and optional
`setup`, `qsub`, `qstat`, `poll_seconds`. The launcher may use `{ranks}`. Ranks
must agree with the allocation and partitioned mesh/checkpoint filenames.
Local jobs can set `timeout_seconds`; PBS uses walltime and exports it as
`CHM_WALLCLOCK_LIMIT` for checkpointing.

PBS scripts source `setup` and invoke the configured launcher directly in that
Bash shell. This preserves site-specific `mpirun` functions (and aliases when
the setup enables alias expansion), as well as its exported environment.
Short-lived Python helpers check checkpoint progress before and after CHM;
they do not launch MPI as a Python subprocess.

PBS model runs queue a dependency chain of up to `model.max_runs` jobs (default
10), each with `model.job.walltime`. The Western example therefore allows up to
ten six-hour allocations for a backfill. Jobs use `afterok` dependencies and
share one prepared CHM configuration and forcing snapshot. CHM must enable
`checkpoint.save_checkpoint`, `checkpoint.on_wallclock_limit`, and
`checkpoint.auto_resume` when more than one segment is allowed; the Western
configuration enables all three and checkpoints five minutes before walltime.

A segment that exits successfully with a new checkpoint releases the next job.
`clean_exit` finishes the chain and permits postprocessing. Errors, no checkpoint
progress, or reaching `max_runs` stop the chain and retain checkpoints. Each
queued script checks a permanent chain-completion marker before environment
setup, so unused segments never restart CHM. The first unused segment exits 99
to stop further `afterok` dependencies; that guard exit does not mark an already
completed model run as failed. Explicit retry codes/attempts within a PBS model
segment run inside that allocation, with the remaining walltime passed to CHM.

`run` prepares, executes CHM and postprocesses. `run --no-postprocess` stops after
CHM. `postprocess` processes existing model output without rerunning CHM.
`model.output_file` (default `output.nc`) selects the project's fixed NetCDF
filename. Preparation sets CHM's generated `output.output_dir` to `output` and
`output.ugrid.base_name` to that filename without `.nc`, so CHM and the
postprocessor use the same file. Authored configuration is not rewritten.
NetCDF is required; UGRID rotation is currently unsupported by this fixed-file
postprocessor and is rejected instead of silently exporting an older file.
Checkpoint-restored UGRID paths must also name this project-owned file.
Validation runs before CHM launches (including each new PBS segment) and before
postprocessing. An output symlink cannot be used to share a legacy NetCDF.

`run` prints progress by default: forcing coverage, the latest checkpoint,
PBS submissions and job IDs, log paths, checkpoint continuation, and the
number/date range of output timesteps selected for postprocessing. Messages
include a UTC timestamp and project ID, and are flushed immediately to stderr
so they appear in redirected cron logs. PBS waits report scheduler state
changes and a heartbeat every five minutes (at the next configured poll).
Detailed CHM/MPI output stays in the reported job logs; this is stage progress,
not a live model timestep counter. The final result remains on stdout.

Use `snowcast run PROJECT --quiet` (or `-q`) to suppress progress while retaining
the final result and errors. Capture both streams in cron with `>> run.log 2>&1`.
For backfills, check the reported export dates: `postprocess.recent_steps`
defaults to two output timesteps. Increase it to include the required dates
still present in `output.nc`; if the model is already `up_to_date`, invoke
`snowcast postprocess PROJECT` explicitly because `run` skips that stage.

A project lock excludes duplicate writers, including a local job whose runner
was killed. PBS pending submissions are recovered before changing staged
configuration or forcing. This means `prepare` may wait for an already-running
PBS job to finish, although it never submits a new one.

Once submitted, the model chain continues even if the launching `snowcast`
process disconnects. Rerun `snowcast run PROJECT` to reconnect; it waits on the
existing chain and postprocesses its completed output without submitting the
model again. It also completes a partially submitted chain when all prior job
IDs are known. `prepare` waits on known jobs but never submits missing segments.
An uncertain `qsub` acknowledgement still needs operator resolution.

If `qsub` acknowledgement is lost, inspect the scheduler and the project's
`work/jobs/*.pending.json` (or the segment record inside a chain directory).
Once the actual job ID is known, set `state` to
`submitted` and `job_id` to that ID, then retry. Clear pending state only after
confirming that its job is no longer running. If the batch exit file is missing,
the runner also checks `qstat -xf`. A finished history record with an exit status
resolves that job; unknown jobs, missing exit status, or scheduler outages retain
pending state and show the scheduler error.

Failures stop subsequent stages and record details in `work/status.json`.
Retries are opt-in via `attempts`, `retry_codes`, `retry_delay_seconds`.
`model.no_data_codes` can map explicit nonzero exits to `up_to_date`. A checkpoint
at or beyond the forcing end also produces `up_to_date`; both cases skip
postprocessing. To retry a failed postprocess independently, use `postprocess`.

Successful CHM completion requires `clean_exit`. Exit zero without it continues
only when a checkpoint was created or updated, up to `max_runs` (10). No progress
fails immediately. Checkpoint retention defaults to the newest three date groups;
it is independent of web history and does not reset the model on September 1.

Notifications are disabled by default. Optional
`"notifications": {"webhook_env": "SNOWCAST_WEBHOOK_URL"}` sends an HTTPS JSON
failure message using the URL from that environment variable. Credentials stay
out of the manifest; notification failure does not mask the original error.

## Postprocessing

The current adapter supports `swe`, `snowdepthavg`, and `t`. Domain locations
and project counts are arbitrary; additional model variables or engines need
an adapter change. The default exporter is `chm_ugrid2grid`, using the latest
two output timesteps, a 0.001-degree source grid and conservative remapping.
It exports a geographic intermediate. SnowCast reprojects when the configured
target grid differs; this adds resampling rather than performing direct
conservative mesh-to-projected-grid export.

The first complete export establishes `work/postprocess/grid.json`. A matching
source retains its exact transform, including small nominal-resolution
rounding differences. Later dates must match that source grid. Changed grid
settings require a separate project/workspace and rebuilt history.

All requested variables and timestamps are checked before rotating current
products into the project's archive. TIFFs retain Float32/Float64 precision,
masks, nodata and scale/offset. Reprojection combines masks and nodata before
interpolation. Optional ASCII exports contain physical values, use EPSG:4326
and `-9999` nodata, and select the latest exported timestamp. COG publication
continues to use Float32; source TIFFs are not converted to that precision.

## Migration from the nested version 1 manifest

1. Create a separate folder and version 2 manifest for each old domain. Merge
   that domain's settings over the old defaults, then place `model`, `forcing`,
   `postprocess` and `display` at the top level. Give it its own stable ID.
2. Copy authored CHM/environment files into the project, or reference shared
   inputs explicitly. Rebase relative paths for their new locations. Remove
   `work_root`, `defaults`, `domains`, and `--domain` from commands.
3. Run `validate`, then `prepare`; inspect the resolved configuration, forcing
   snapshot, start date and actual PBS settings.
4. With the old writer stopped and no pending PBS jobs, copy compatible
   checkpoints into the new project's `work/chm/output/checkpoint/`. Check CHM
   version, mesh and rank compatibility first. Do not share mutable state.
   For the prior runner, the source was `<old-work-root>/<domain>/chm/output/`;
   the legacy workflow used `run_chm/output/`.
   Copy the corresponding UGRID NetCDF as well, and update the copied
   checkpoint's `ugrid_outputs[].path` to its new absolute destination. CHM
   restores this path from the checkpoint even when its output configuration
   names a different file. See the recovery procedure below.
5. Do not copy old ownership markers, pending job records or generated scripts:
   they contain old identities/absolute paths. Retain original logs for reference.
   Historical postprocessed products can be copied with their matching
   `grid.json` only if the project/grid is unchanged.
6. Manually verify one model run and postprocess on the cluster before replacing
   its cron invocation. Automated fixtures do not replace a real CHM/MPI/PBS check.

The old `python snowcast.py -c config_hrdps_west.py` entry point, its Python
settings files, fixed PBS/cron scripts, plotting/v2 upload pipeline, and
compatibility modules have been removed. Use the installed `snowcast` commands.
The old source remains available in Git history. Existing output directories,
external archives and production crontabs are not deleted or changed by this
repository cleanup. Version 1 manifests still report an explicit migration error.

A cron entry should invoke the installed executable for one project, for example:

```cron
0 12 * * * /path/to/environment/bin/snowcast run /projects/western-cordillera >> /projects/western-cordillera/run.log 2>&1
```

Set the actual environment path and schedule for your installation. Model and
postprocessing environment setup is specified by that project's `job.setup`.
Publication remains a separate command; sequence it after a successful run when
configuring deployment. No cron entry is installed by SnowCast.

## Recovering output written to a legacy workspace

If CHM reaches a newer date but successful postprocessing still reports older
dates, compare `model.output_file` with the latest checkpoint's
`ugrid_outputs[].path`. A copied checkpoint can make CHM append to the legacy
NetCDF while SnowCast reads an older copy in the new project. Changing
`recent_steps`, republishing, or simply rerunning CHM does not repair that path.

1. Stop scheduled launches for both workflows and wait until neither has an
   active or queued model/regridding job. The old and new outputs must be idle
   while copying data and editing checkpoint metadata.
2. Find the updated legacy NetCDF from the checkpoint's UGRID entry. Confirm
   its time axis includes the missing dates and that it belongs to this same
   model/mesh. The destination is the new project's
   `work/chm/output/<model.output_file>`.
3. Back up the destination and copy the complete updated NetCDF into it. Keep
   the legacy file intact; do not link the two workflows' mutable output files.
   For the default filename, this example preserves an existing destination
   under a dated backup name (replace the source path):

   ```bash
   rsync -ah --progress --backup --suffix=".before-recovery-$(date +%Y%m%dT%H%M%S)" \
     /absolute/path/to/legacy/output.nc \
     projects/western-cordillera/work/chm/output/output.nc
   ```

4. Back up the latest JSON checkpoint **inside the new project**, then change
   its matching `ugrid_outputs` entry's `path` to the destination's absolute
   path and `base_name` to `model.output_file` without `.nc`. Keep its simulation
   time, timestep counter, rank count, `files` list and rank-state files intact.
   Store the backup with a suffix after `.json` so auto-resume cannot select it.
   Do not edit the legacy workflow's checkpoint. Older copied checkpoints also
   need this correction before deliberately restoring one of them.
5. Regenerate and verify the staged configuration, then process and publish the
   already-computed results:

   ```bash
   snowcast prepare projects/western-cordillera &&
   snowcast postprocess projects/western-cordillera &&
   snowcast publish sites/snowcast.json --project western-cordillera
   ```

   `postprocess.recent_steps` must include the desired dates in the copied
   NetCDF. `snowcast status projects/western-cordillera` reports the accepted
   export timestamps. If HPFX/download mirrors are configured, run
   `snowcast archive projects/western-cordillera` after postprocessing and before
   publishing to update those originals and their download listings as well.

The path checks intentionally do not copy large NetCDF files or modify
checkpoint metadata automatically. Pulling this fix prevents further mismatched
runs/exports; existing workspaces still need the above recovery once.

## Original daily download archives

Use `snowcast archive PROJECT` for original TIFF/ASCII uploads. Configure one or
more `local`, `rsync` (including HPFX), or S3-compatible destinations in the
project's JSON or a referenced JSON file. This is independent of Web UI
publication; `publish` only advertises links from completed archive receipts.

See the [archive configuration and migration guide](ARCHIVING.md) for JSON
examples, preserving existing HPFX paths, mirrors, private backups, dry runs,
retry behavior and daily command order.

```bash
snowcast archive projects/western-cordillera --dry-run
snowcast archive projects/western-cordillera
snowcast publish sites/snowcast.json --project western-cordillera
```

## Publication

Use the [site configuration](../sites/README.md) for both remote and local
publication. Populate the observation cache and configure the site once, then
publish each project independently:

```bash
snowcast download-data canswe
snowcast site configure sites/snowcast.json --upload
snowcast publish sites/snowcast.json --project western-cordillera
```

`publish` uploads by default. For local-only testing, configure without
`--upload` and add `--no-upload` to `publish`. It writes the same COGs and
`data/<project-id>/catalog.json` in the site's configured staging directory.
There is no separate `site publish` command or project/`--site-dir` publish form.
Publication also subsets cached observations for the chosen project and merges
its station contribution with the other published projects. Publish every project
once when adopting the observation registry. `publish` does not configure the
site, download sources, or build/deploy the UI. See the
[command table](../sites/README.md#what-each-command-does) and
[migration sequence](../sites/README.md#first-setup-or-migration).

UI installation remains separate. For a local/mounted site:

```bash
snowcast deploy-ui --dist /path/to/webui/dist --site-dir /path/to/staging-site
```

`deploy-ui` copies a completed build locally; it does not invoke npm or SSH. For
a remote website, follow the [UI build/upload commands](../sites/README.md#build-and-deploy-the-ui),
which preserve observation and model data.

Publication preserves safe COG conversion, concurrent registry updates,
hydrological-year selection and 48-hour orphan cleanup. SWE/SD retain ten daily
dates plus older weekly snapshots from September 1 of the latest model date's
hydrological year; temperature retains ten daily dates. Daily source archives
remain daily. The flat per-project catalogue can still be opened directly with
`?catalog=./data/western-cordillera/catalog.json`.

The flat URL differs from the earlier `data/<project>/<domain>/` location. No
live catalogues or URLs are migrated automatically. Original archive download
integration, production namespace migration and scheduling remain separate
from site publication. UI installation preserves published data and site config.

## Development checks

From the repository root, install test/build dependencies and run:

```bash
python -m pip install -e . pytest 'setuptools>=68' wheel
python -m pytest -q tests
```

The suite builds and installs a wheel from only `snowcast_runner` and
`pyproject.toml`, then runs a fixture project through postprocessing outside the
checkout with legacy imports blocked. CHM and exporter stand-ins write small
NetCDF/GeoTIFF fixtures. Scheduler tests simulate PBS acknowledgements and
failures; they do not submit real cluster jobs.
