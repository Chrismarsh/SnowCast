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

After configuring a website using the [site guide](sites/README.md), publish a
project's postprocessed output with:

```bash
snowcast publish sites/snowcast.json --project western-cordillera
```

This uploads by default. Add `--no-upload` to generate the same COGs and catalogue
in local staging without contacting the webserver. UI builds and uploads remain
separate from model-data publication.

## Repository guide

| Location | Purpose |
| --- | --- |
| `snowcast_runner/` | Installed CLI, model orchestration, met indexing, postprocessing and publication utilities |
| `projects/` | Independent project examples and their configuration guide |
| `sites/` | Shared website configuration, independent publication and map guide |
| `webui/` | Static map, downloads, help and about pages |
| `scripts/` | UI data preparation/diagnostics and scientific example configurations |
| `domain/` | Standalone mesh/domain preparation tools |
| `tests/` | Runner, raster, publication and data-preparation checks |
| `spack.yaml`, `spack.lock` | CHM and scientific Python environment specifications |

The [web UI guide](webui/README.md) covers COG generation, daily/weekly map
history, point sampling, observations and Apache/NGINX hosting. The
[site guide](sites/README.md) covers selecting projects, independent uploads and
simultaneous map display with domain-aware colour ranges.

SnowCast output is experimental. See [snowcast.ca](https://www.snowcast.ca/).
