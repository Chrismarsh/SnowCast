# SnowCast

[![Checks](https://github.com/Chrismarsh/SnowCast/actions/workflows/webui.yml/badge.svg)](https://github.com/Chrismarsh/SnowCast/actions/workflows/webui.yml)

SnowCast runs the Canadian Hydrological Model (CHM) and presents simulated snow
water equivalent, snow depth and temperature. It is developed through
collaboration between Environment and Climate Change Canada and the Centre for
Hydrology, University of Saskatchewan.

Each model domain/run is an independent **project folder**, with its own CHM
configuration, forcing references, execution settings, checkpoints and products.
The installed **`snowcast_runner`** package contains the reusable implementation.
The **`webui`** application has a separate build and deployment lifecycle.

## Install and run

From the repository root, where `pyproject.toml` is located, install into your
existing CHM/Spack Python environment:

```bash
python -m pip install -e .
snowcast validate projects/western-cordillera --config-only
```

Copy the Western example to your project location and set its mesh, met archive
and environment paths. Then run:

```bash
snowcast validate /projects/western-cordillera
snowcast prepare /projects/western-cordillera
snowcast run /projects/western-cordillera
```

See the [project guide](projects/README.md) for CHM overrides, forcing metadata,
PBS execution, postprocessing and migration. The old `snowcast.py` entry point,
Python settings files and compatibility wrappers have been removed. Model jobs
and checkpoints live inside the project, not the tool checkout.

## Website setup and daily operation

Start with the [complete site workflow](sites/README.md): first setup/migration,
command responsibilities, daily updates, parallel projects, local previews and
troubleshooting. It includes the copy-paste UI deployment commands for
`/v3-testing/`.

Website setup separates observation downloads, site configuration, project
runs/publication and UI deployment. Original archives have their own command.
**`publish` uploads model and observation data by default; it does not
run `site configure`, download CanSWE, archive originals, or build/deploy the UI.**

After the [one-time setup](sites/README.md#first-setup-or-migration), routine
operation is one run and one publish per project:

```bash
snowcast run projects/western-cordillera &&
snowcast publish sites/snowcast.json --project western-cordillera

snowcast run projects/tvc &&
snowcast publish sites/snowcast.json --project tvc
```

For original TIFF/ASCII storage, configure [archive destinations](projects/ARCHIVING.md)
in JSON and insert `snowcast archive PROJECT` between `run` and `publish`.
Archive backends include local/mounted storage, SSH/rsync (HPFX), and S3-compatible
object storage. `publish` only supplies the Web UI with completed archive links.

The project pairs can run independently. Use `--no-upload` on publication for
local staging only. Changing UI code requires a separate npm build and UI upload;
changing model dates or already-supported observation data does not.

## Repository guide

| Location | Purpose |
| --- | --- |
| `snowcast_runner/` | Installed CLI, model orchestration, met indexing, postprocessing and publication utilities |
| `projects/` | Independent project examples and their configuration guide |
| `sites/` | End-to-end setup, daily publication, observation cache, UI deployment and troubleshooting |
| `webui/` | Static map, downloads, help and about pages |
| `scripts/` | Synthetic UI demos, diagnostics and scientific example configurations |
| `domain/` | Standalone mesh/domain preparation tools |
| `tests/` | Runner, raster, publication and data-preparation checks |
| `spack.yaml`, `spack.lock` | CHM and scientific Python environment specifications |

The [web UI guide](webui/README.md) covers COG generation, daily/weekly map
history, point sampling, observations and Apache/NGINX hosting. The
[site guide](sites/README.md) covers selecting projects, independent uploads and
simultaneous map display with domain-aware colour ranges.

SnowCast output is experimental. See [snowcast.ca](https://www.snowcast.ca/).
