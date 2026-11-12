#!/bin/bash
# Sourced inside this project's model and postprocessing jobs.
# Resolve the checkout root from this file, not the batch job's working directory.
SNOWCAST_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

# The Western cluster profile initializes Spack and other site settings.
source "${HOME}/.profile"

# Projects copied outside the checkout can select another environment by setting
# SNOWCAST_SPACK_ENV here or in ~/.profile; PBS need not inherit the login shell.
spack env activate "${SNOWCAST_SPACK_ENV:-$SNOWCAST_REPO_ROOT}"
