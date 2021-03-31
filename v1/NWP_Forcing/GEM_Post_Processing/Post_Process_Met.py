'''
Apply statistic model to adjust numerical weather output based on gridded observed data

'''
import PP
import dask.multiprocessing
import datetime
import imp
import json
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
import seaborn as sns
import sys
import time
import xarray as xr
from dask import compute, delayed
from scipy.interpolate import griddata

import idw

start_time = time.time()
# Hack to force datetimes to display in GMT/UTC (numpy 1.11.1 has fixed this but other dependent modules (pynio) can't handel numpy 1.11.1)
os.environ['TZ'] = 'GMT'
time.tzset()

# General plotting settings
sns.set_style('whitegrid')
sns.set_context("talk", font_scale=1.5, rc={"lines.linewidth": 2.5})
fig_res = 90 # dpi

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) != 2:
    sys.exit('Requires 1 argument [configuration file] ')

# Get name of configuration file/module
configfile = sys.argv[1]
# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
data_dir = X.data_dir
git_dir = X.git_dir

# Target GEM files
gem_run = 'Historical'
# gem_run = 'Current'

# Load in info on GEM data (in ascii format)
if gem_run == 'Current':
    main_gem_dir = '/media/data3/nicway/GEM/west/'
    ascii_in_dir = 'CHM_archive'
    json_config_file = 'GEM_forcing.json'
elif gem_run =='Historical':
    main_gem_dir = '/media/data3/nicway/GEM/archive/SOAP/'
    ascii_in_dir = 'ascii_HRDPS_SnowCast_full'
    json_config_file = 'SOAP_forcing.json'

GEM_config_file = os.path.join(main_gem_dir, ascii_in_dir, json_config_file)
gem_files = json.load(open(GEM_config_file))

# Load in Gridded Obs file
obs_file = os.path.join(data_dir, 'QC', gem_run+'_Gridded.nc')
ds_obs = xr.open_dataset(obs_file)

# Dictonary of obs var name to CHM var names
vars_all = {'AirtemperatureA':'t','AirMoistureContentA':'rh','IncrementalPrecipitationA':'p',
            'ScalarWindSpeedA':'U_2m_above_srf','DownwardSolarRadiation':'iswr','DownwardTerrestrialRad':'ilwr',
            'UpwardTerrestrialRad':'ilwr_out',
            'SnowWaterEquivelentA':'swe','SnowDepthA':'snowdepthavg','WindDirectionatA':'vw_dir',
           'Time_UTC':'datetime'}
# Trim to variables contained in ds_obs
vars_new = { your_key: vars_all[your_key] for your_key in ds_obs.data_vars }
ds_obs = ds_obs.rename(vars_new);
print(ds_obs)

# Output corrected GEM dir
ascii_out_dir = 'Bias_p'
output_gem_dir = os.path.join(main_gem_dir, ascii_out_dir)
GEM_config_file_out = os.path.join(main_gem_dir, ascii_out_dir, json_config_file)
if not os.path.exists(output_gem_dir):
    os.makedirs(output_gem_dir)



# Initialize df to save stats
df_stats = pd.DataFrame(index=gem_files.keys(),
                        columns=['orig_Bias', 'adj_Bias'])

# Wrapper functoin to adjust the bias of one forcing file
def bias_adjust(cf=None, cinfo=None, cvarible=None,
                observations=ds_obs, output_gem_dir=output_gem_dir):
    print(cf)
    # Create new point forcing class
    cpt = PP.point_forcing(cinfo=cinfo,
                           ds_grid_obs=observations,
                           cvariable=cvarible)

    # Define calibration and evaluation periods
    wyrs = cpt.define_cal_val_periods(method='water_year')

    # Fit model
    (model_bias, true_bias) = cpt.fit_simple_bias_model(periods=wyrs)

    # Modify in place CHM forcing for variable X
    df_adj = cpt.apply_bias(periods=wyrs, model_bias=model_bias, cvariable=cvarible)

    # Write out to new output_dir
    file_out = os.path.join(output_gem_dir, cf + '.chm')
    cpt.write_to_ascii(df_out=df_adj, file_out=file_out)

    return (model_bias, true_bias)


# Loop through each GEM file (grid cell)
values = []
for cf, cinfo in gem_files.iteritems():
    # cf = 'point_0_7'
    # cinfo = gem_files[cf]
    values.append(delayed(bias_adjust)(cf, cinfo, 'p',
                 ds_obs.copy(), output_gem_dir))

    # Update config file with new file path
    file_out = os.path.join(output_gem_dir, cf + '.chm')
    gem_files[cf]['file'] = file_out

print("computing")
# values = [delayed(bias_adjust)(cf,cinfo,'p') for cf in all_files]
# results = compute(*values, get=dask.multiprocessing.get) # multi preocessors
# results = compute(*values, get=dask.threaded.get) # multi threads
results = compute(*values, get=dask.get)   # Single (for debugging)
print("--- Took %s minutes ---" % ((time.time() - start_time)/60))

# Write out json file with metadata to new path
with open(GEM_config_file_out, 'w') as outfile:
    json.dump(gem_files, outfile,indent=4, sort_keys=True)


