# Independent SnowCast projects

One project is one independently configured CHM domain/run. Its folder owns its
configuration, generated jobs, forcing metadata, checkpoints, outputs and
processed products. The installed `snowcast_runner` package owns the reusable
implementation. Projects do not depend on the SnowCast checkout or on one another.

A separate site configuration will select projects for a shared website. That
site configuration and the simultaneous multi-project map are the next stage;
this stage implements independent projects through postprocessing.

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
- `environment.sh` to load your installed CHM/pyCHM/MPI environment, or leave its
  no-op setup if the invoking environment already supplies those executables.
- The model and postprocessing PBS allocations for your cluster.

The example contains explicit placeholder paths; it does not guess a production
installation or adopt existing checkpoints. Its authored configuration is
independent of `run_chm/`, `met/`, and other legacy checkout directories.

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
| `work/chm/output/` | Model output, `clean_exit`, and `checkpoint/` |
| `work/jobs/` | Generated scripts, execution logs, exit results and pending PBS submissions |
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

Mesh paths resolve relative to the configuration file that declares each mesh
entry. An override can therefore replace an absent base mesh before validation.
Errors identify the project, key, source configuration, resolved path and rank
mismatch where relevant. Other module-specific file inputs should use absolute
paths or explicit `model.assets` aliases, which create read-only input references
in the execution directory. Arbitrary CHM strings are not guessed to be paths.

After resolution, SnowCast supplies `forcing.file`, `output.output_dir`, the
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
aliases and the legacy runner. A small archive-binding file next to the index
prevents two independent projects from updating one index from different
archives. Different start dates filter independent snapshots without removing
shared history. Use separate indexes for separate archives. If an archive is
relocated, create a new index for its new location instead of mixing paths.

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

`run` prepares, executes CHM and postprocesses. `run --no-postprocess` stops after
CHM. `postprocess` processes existing model output without rerunning CHM.
`model.output_file` (default `output.nc`) must match the actual CHM output
filename; it tells the postprocessor which file to read.

A project lock excludes duplicate writers, including a local job whose runner
was killed. PBS pending submissions are recovered before changing staged
configuration or forcing. This means `prepare` may wait for an already-running
PBS job to finish, although it never submits a new one.

If `qsub` acknowledgement is lost, inspect the scheduler and the project's
`work/jobs/*.pending.json`. Once the actual job ID is known, set `state` to
`submitted` and `job_id` to that ID, then retry. Clear pending state only after
confirming that its job is no longer running. A failed `qstat` without a result
retains pending state and does not trigger another submission.

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
5. Do not copy old ownership markers, pending job records or generated scripts:
   they contain old identities/absolute paths. Retain original logs for reference.
   Historical postprocessed products can be copied with their matching
   `grid.json` only if the project/grid is unchanged.
6. Manually verify one model run and postprocess on the cluster before replacing
   its cron invocation. Automated fixtures do not replace a real CHM/MPI/PBS check.

The old `python snowcast.py -c config_hrdps_west.py` workflow remains available.
Its reusable met and COG entry points delegate to the installed package. Legacy
plotting and v2 upload orchestration remain checkout-only compatibility code.
The new runner does not invoke them. Version 1 manifests produce an explicit
migration error; existing run directories are never moved automatically.

## Existing publication helpers and the next stage

The existing local/mounted publication helper remains available with a flat
project identity:

```bash
snowcast publish /projects/western-cordillera --site-dir /path/to/staging-site
snowcast deploy-ui --dist /path/to/webui/dist --site-dir /path/to/staging-site
```

It writes `data/<project-id>/catalog.json`, preserving safe COG conversion,
concurrent registry updates, hydrological-year selection and 48-hour orphan
cleanup. SWE/SD retain ten daily dates plus older weekly snapshots from September
1 of the latest model date's hydrological year; temperature retains ten daily
dates. Daily source archives remain daily. This refactor does not change COG
encoding or digest algorithms.

These helper commands do not implement the planned authoritative site config or
remote multi-project deployment. The existing legacy SSH uploader remains a
separate compatibility entry point. UI deployment preserves published data.

The viewer still loads one catalogue, for example
`?catalog=./data/western-cordillera/catalog.json`. The new flat URL differs from
the earlier `data/<project>/<domain>/` location. No live catalogues or URLs are
migrated automatically. Production namespace migration, total storage planning,
site selection and the multi-project map belong to the next stage.

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
