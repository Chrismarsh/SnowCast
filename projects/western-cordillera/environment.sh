#!/bin/bash
# Sourced inside this project's model and postprocessing jobs.
# The Western cluster profile initializes Spack and other site settings.
source "${HOME}/.profile"

# Keep using the existing Western CHM/pyCHM environment, independently of where
# this project lives. Edit this path or set SNOWCAST_SPACK_ENV in ~/.profile
# when using a different installation; PBS need not inherit the login shell.
spack env activate "${SNOWCAST_SPACK_ENV:-/home/chm003/project/Snowcast-www/SnowCast}"
