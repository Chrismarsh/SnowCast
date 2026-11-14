# Original model archives

`snowcast archive PROJECT` transfers original TIFF/ASCII products to storage.
`snowcast publish SITE_CONFIG --project ID` publishes Web UI backend data: map
COGs, observations, and download links from completed archives. Neither command
runs the other. Archiving does not require a configured website or observation
cache, and does not build/deploy the UI.

## Configure destinations in JSON

Add `archive` to each project's `snowcast.json`. Either supply the object inline,
or reference another JSON file:

```json
{
  "archive": "../../archive-destinations.json"
}
```

This is a field to add to an existing version 2 project, not a complete project.
The referenced file contains the same object as an inline `archive` value:

```json
{
  "destinations": [
    {
      "id": "hpfx",
      "name": "HPFX",
      "backend": "rsync",
      "host": "collab-lp",
      "directory": "/absolute/path/to/public/archive/{project}",
      "public_url": "https://hpfx.collab.science.gc.ca/~chm003/archive/{project}/"
    },
    {
      "id": "local-backup",
      "name": "Local backup",
      "backend": "local",
      "directory": "/storage/snowcast-archive/{project}"
    },
    {
      "id": "object-storage",
      "name": "Object storage",
      "backend": "s3",
      "bucket": "snowcast-data",
      "prefix": "archive/{project}",
      "profile": "snowcast",
      "region": "ca-central-1",
      "endpoint_url": "https://s3.example.org",
      "public_url": "https://downloads.example.org/archive/{project}/"
    }
  ]
}
```

These are placeholders. Keep only the destinations you intend to use, and set
actual paths/URLs. Nothing is enabled by default. IDs must be unique.
`{project}` expands to the model project's ID in `directory`, `prefix` and
`public_url`. Other substitutions are rejected. Relative local directories are
resolved against the JSON file containing the destination definitions.

| Backend | Required settings | Runtime requirements |
| --- | --- | --- |
| `local` | `directory` | Local or mounted writable directory outside project `work/` |
| `rsync` | `host`, absolute `directory` | SSH/rsync on the runner; rsync and Python 3 on the destination |
| `s3` | `bucket`, nonempty `prefix` | AWS CLI v2; an existing bucket and read/write access to the prefix |

`name` and `public_url` are optional on every destination. Without `public_url`,
the destination is a private backup and is omitted from the Downloads page.
For S3, `profile`, `region` and `endpoint_url` are optional. Omit `endpoint_url`
for AWS; set it for compatible object storage. The endpoint must support
conditional object creation (`If-None-Match: *`). Credentials come from SSH or
the AWS CLI's normal credential configuration, not this JSON. SnowCast does not
create buckets or change access policies. A public URL must already serve the
configured storage root; configuring it does not make files public.

Every root contains `tiff/`, `asc/` and `archive-index.json`. It belongs to one
project, enforced by an ownership marker. Different projects need separate roots
or prefixes. Multiple destinations may mirror the same project. The project
workspace lock prevents `run`, `postprocess`, `archive` and `publish` from
modifying that project's products concurrently; different projects can operate
independently. Use one writer/workspace per project and archive root.

## Commands and order

```bash
# Inspect the plan without connecting to or writing any destination.
snowcast archive projects/tvc --dry-run

# Archive to every configured destination, or select one by ID.
snowcast archive projects/tvc
snowcast archive projects/tvc --destination hpfx

# Publish the map, observations and completed public archive links afterward.
snowcast publish sites/snowcast.json --project tvc
```

Repeat `--destination` to select several destinations. `--force` resends all
locally available products, useful after restoring or repairing remote storage.
The default uses local completion receipts plus size/mtime/ctime to avoid
resending unchanged products. It does not audit remote objects on every run.
No destination is contacted by `--dry-run`; workspace locking may create local
lock/ownership files, but no archive receipt is committed.

For daily operation with an archive:

```bash
snowcast run projects/tvc &&
snowcast archive projects/tvc &&
snowcast publish sites/snowcast.json --project tvc
```

Archival is optional: `run` followed directly by `publish` still updates the map
and observations. If you publish first, run `publish` again after archival to
refresh the Web UI's download links. The `&&` sequence above deliberately stops
before publication if any archive destination fails; operators can schedule the
two commands independently when map availability should not depend on archives.

## Retention, failures and download links

Archiving reads each project's `postprocess/archive_tiff`, `tiff`,
`archive_ascii` and `ascii` folders. Current revisions take precedence over
archived copies with the same filename. Masks, overviews, PAM metadata and ASCII
projection files travel with their rasters. ASCII is archived when products
exist; this command does not generate missing formats or dates.

Only new/changed files are transferred. Old remote files are never deleted;
map retention and COG cleanup do not affect these originals. Remote indexes are
written after successful file transfers. Local/SSH indexes are replaced
atomically; S3 uploads a complete index object. A failed destination retains its
previous completion receipt, successful mirrors are still recorded, and the
command exits nonzero. Retry the same command after fixing the destination.
Individual revised rasters can already have been replaced when a later transfer
fails: this is not a transactional snapshot of the entire archive.

Receipts live in `PROJECT/work/archive/DESTINATION.json`. Preserve them when
moving a project: they retain knowledge of previously uploaded dates even when
those local source files are no longer present. Changing a destination's
configuration requires successful archival to that new configuration before its
links are advertised. Removing a destination removes its links on the next
`publish`, without deleting its files. A revision that removes a previously
uploaded companion file is rejected, to avoid leaving a stale mask/metadata
file affecting the raster. Restore the companion or choose a new archive root.

`publish` copies public receipt metadata to `data/PROJECT/downloads.json`, locally
and to the configured Web UI host. It never contacts the archive backend or
uploads original rasters. No SSH hosts, storage paths, bucket settings or
credential profiles are exposed in this public index. The Downloads page lets
visitors choose project, archive mirror, format/grid, variable and dates. Grid
spacing and CRS come from project metadata; a missing project's downloads never
fall back to another project's files. Routine index updates need no npm build.

## Existing HPFX archives

The SSH alias `collab-lp` is only an example; set your actual alias/account. For
Western Cordillera, keep the existing storage parent of `tiff/` and `asc/` as
`directory`, and use `https://hpfx.collab.science.gc.ca/~chm003/` as `public_url`.
This preserves its existing file URLs. Give TVC a separate root, for example
`.../tvc/` with public URL `https://hpfx.collab.science.gc.ca/~chm003/tvc/`.
Do not use the Western parent as TVC's root.

The new index covers products present locally plus prior successful receipts.
Remote-only historical files remain untouched and retain their URLs, but are
not discovered automatically. To include them in the project's new index,
restore those originals and sidecars to its `archive_tiff`/`archive_ascii`
folders before archiving. Do not mix different projects or grid definitions.

Older single-project websites without `site.json` can still use the legacy
`download-index.json` listing. Unified websites use per-project download indexes;
the old hardcoded Western listing is not used as a fallback for missing projects.

## Backend extension

Storage operations are isolated behind `claim`, `transfer` and `commit` in
`snowcast_runner/archive.py`. Add a backend's strict JSON validation, register its
adapter in `BACKENDS`, and test transfer/ownership/failure behavior. Keep project
inventory, receipts and Web UI metadata independent of storage transport.

The S3 adapter uses the official AWS CLI [copy command](https://docs.aws.amazon.com/cli/latest/reference/s3/cp.html)
and [conditional object creation](https://docs.aws.amazon.com/cli/latest/reference/s3api/put-object.html).
