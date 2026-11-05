

import slack_webhook
import os

settings = dict()

# Should snowcast run in a mode that allows CHM to checkpoint.
settings['checkpoint_mode'] = True

# how many of the most recent daily checkpoints to keep (older ones are
# pruned after each successful CHM run; CHM auto-resumes from the newest)
settings['checkpoint_keep_days'] = 3

# the URL to use for the slack webhook. This is a secret
settings['webhook_url'] = slack_webhook.webhook_url

settings['snowcast_base'] = os.getcwd()

# where to put the nc file CHM to use
settings['nc_chm_dir'] = os.path.join(settings['snowcast_base'], 'met')

#active configuration path
settings['chm_config_path'] = os.path.join(settings['snowcast_base'], 'run_chm/config.json')

# where the CHM output is
settings['chm_outpath'] = os.path.join(settings['snowcast_base'], 'run_chm/output/SC.nc')

# where to put the leaflet output
settings['html_dir'] = os.path.join(settings['snowcast_base'], 'www')

# how should CHM be called?
#settings['chm_exec_str'] = '%s -f config.json.chkp.json' % os.path.join(settings['snowcast_base'], 'run_chm/CHM')
settings['chm_exec_str'] = './submit_snowcast_job.sh'


# if there are more nc than you'd like to include, start at this date
# if None, use earliest available
# Format Y-M-D
settings['start_date'] = '2025-09-01'

# post processing settings
# these are using the pvd -> tiff step

# the ESMF regridder can expand to a whole cluster via MPI. This allows for calling it via, e.g, slurm
# if this key is not present it will default to local node MPI using postprocess_maxprocs processors
# if postprocess_exec_str is defined, postprocess_maxprocs is ignored
# settings['postprocess_exec_str'] = './submit_to_prioQ.sh postprocess/job.sh'
#settings['postprocess_maxprocs'] = 8

#same as above but for plot generation
# settings['plotgen_exec_str'] = 'mpirun --mca btl tcp,self --mca btl_tcp_if_include ibs1 --hetero-nodes -n 75 gdal2tiles '
# settings['plotgen_maxprocs'] = 8

#variables to plot (implicitly includes the difference between these)
settings['plot_vars'] = ['swe', 'snowdepthavg', 't']

# Optional v3 COG publishing. Enable after deploying webui/dist to your web host.
# The existing Leaflet viewer and AEP exports remain available during migration.
settings['webui_enabled'] = False
settings['webui_keep_days'] = 10
settings['webui_data_dir'] = os.path.join(settings['snowcast_base'], 'postprocess', 'webdata')
# Relative asset URLs work when the catalogue and cogs/ are hosted together.
settings['webui_data_url'] = None
# Set these only when the published data needs to be copied to another machine.
settings['webui_upload_host'] = None  # e.g. 'root@www.snowcast.ca'
settings['webui_upload_dir'] = None   # e.g. '/var/www/html/v3/data'

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
# settings['fig_dir'] = os.path.join(settings['snowcast_base'], 'plot/figures')
# settings['dpi'] = 90
