#!/bin/bash
# Site-specific environment setup, sourced inside the domain's batch job.
source "${HOME}/.profile"
SNOWCAST_CODE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
spack env activate "$SNOWCAST_CODE_DIR"
