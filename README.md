# SnowCast
[![Build Status](https://travis-ci.com/NicWayand/SnowCast.svg?token=rcbpjWbw439hZe2teEp3&branch=master)](https://travis-ci.com/NicWayand/SnowCast)

The [project runner](projects/README.md) separates shared SnowCast software from
domain-specific model inputs, jobs, postprocessing and writable state. Install
with `python -m pip install -e .`, then validate the western example with
`snowcast validate projects/western --config-only`. Real runs require the project
inputs and CHM/MPI/PBS environment; see the migration guide before changing cron.

SnowCast is an experimental data product that uses the Global Environmental Multiscale (GEM) model forecasts from Environment and Climate Change Canada (ECCC) to drive the Canadian Hydrological Model (CHM). Estimates of snowpack are provided over the a Bow River Basin, centered over Banff, Canada.

SnowCast is developed as part of Global Water Futures and the Centre for Hydrology, University of Saskatchewan. Thanks to collaboration with ECCC.

Two GEM forecasts are currently used:

* GEM 2.5 km 2-day forecasts (High Resolution Deterministic Prediction System (HRDPS))
* GEM 25 km 6-day forecasts (Global Deterministic Forecast System (GDPS)

<img src=http://www.snowcast.ca/static/HRDPS/swe_diff.png width="400" align="middle">
Figure 1. Current 1-day forecast change in SWE. Centered over Banff, Alberta, Canada.

http://www.snowcast.ca/

The [COG snowpack explorer](webui/README.md) provides daily/weekly playback,
point histories, and numeric GeoTIFF viewing. Its publishing and hosting guide
includes serving the data from an ordinary disk with Nginx or Apache.

Experimental! Use at your own risk.

