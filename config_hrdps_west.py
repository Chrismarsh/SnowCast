

import slack_webhook
import os

settings = dict()

# Should snowcast run in a mode that allows CHM to checkpoint. Requires a slightly differently handling of the met files
settings['checkpoint_mode'] = True

# the URL to use for the slack webhook. This is a secret
settings['webhook_url'] = slack_webhook.webhook_url

settings['snowcast_base'] = os.getcwd()

settings['hrdps_domain'] = 'continental'

# Dir to put GEM grib2 files
settings['grib_dir'] = os.path.join(settings['snowcast_base'], 'nwp_forcing/grib_download')

# were to copy after we have processed. Not used, just kept "in case"
settings['grib_ar_dir'] = os.path.join(settings['snowcast_base'], 'nwp_forcing/grib_ar')

# Dir where output netcdf files go
settings['nc_ar_dir'] = os.path.join(settings['snowcast_base'], 'nwp_forcing/nc_ar')

# where to put the nc file CHM to use
settings['nc_chm_dir'] = os.path.join(settings['snowcast_base'], 'nwp_forcing')

#where to put the standalone nc files for use with the checkpointing mode
settings['checkpoint_nc_chm_dir'] = os.path.join(settings['snowcast_base'], 'nwp_forcing/ckp_nc')

#active configuration path
settings['chm_config_path'] = os.path.join(settings['snowcast_base'], 'run_chm/config.json')

# where the CHM output is
settings['chm_outpath'] = os.path.join(settings['snowcast_base'], 'run_chm/output/meshes/SC.pvd')

# where to put the leaflet output
settings['html_dir'] = os.path.join(settings['snowcast_base'], 'www')

# how should CHM be called?
#settings['chm_exec_str'] = '%s -f config.json.chkp.json' % os.path.join(settings['snowcast_base'], 'run_chm/CHM')
settings['chm_exec_str'] = './submit_to_prioQ.sh job.sh'

# produce the complete nc archive. Can use a lot of RAM for large nc files and might not be worth the hassle
# esp. if Snowcast is run in chkpoint mode
settings['create_complete_nc_archive'] = False


# force a regeneration of the complete nc archive
settings['force_nc_archive'] = False

# if there are more nc than you'd like to include, start at this date
# doesn't impact grib processing, just the nc -> CHM step
# if None, use earliest available
# Format Y-M-D
# settings['start_date'] = '2020-10-26'
# settings['end_date'] = '2021-03-29'
settings['start_date'] = '2022-09-17'

# regridding resolution
settings['dxdy'] = 0.002

# post processing settings
# these are using the pvd -> tiff step

# the ESMF regridder can expand to a whole cluster via MPI. This allows for calling it via, e.g, slurm
# if this key is not present it will default to local node MPI using postprocess_maxprocs processors
# if postprocess_exec_str is defined, postprocess_maxprocs is ignored
settings['postprocess_exec_str'] = './submit_to_prioQ.sh postprocess/job.sh'
#settings['postprocess_maxprocs'] = 8

#same as above but for plot generation
# settings['plotgen_exec_str'] = './submit_to_prioQ.sh plot/job.sh'
settings['plotgen_maxprocs'] = 8

#variables to plot (implicitly includes the difference between these)
settings['plot_vars'] = ['swe', 'snowdepthavg', 't']

# Offset from UTM to local time (i.e. Mountain standard time = -7)
# CHM forcing files will be in this time zone
# not currently used
local_time_offset = 0

#### [min,max] extents for bounding box of latitude and longitude

# Bow river basin
# lat_r = [50.411581,51.218712]
# lon_r = [-115.793152,-114.362183]

# CRHO (crho_extent.tif)
lat_r = [50.66, 51.7933333333333]
lon_r = [-116.645, -114.769166666667]

# Entire GEM west domain
# lat_r = [0,90]
# lon_r = [-180,180]

#static figure settings
# deprecated
settings['fig_dir'] = os.path.join(settings['snowcast_base'], 'plot/figures')
settings['dpi'] = 90
