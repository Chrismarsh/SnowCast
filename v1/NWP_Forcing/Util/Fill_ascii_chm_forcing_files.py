import os
import glob
import imp
import sys
import time
import utm
import matplotlib.pyplot as plt
import dask.multiprocessing
from dask import compute, delayed
import chm_forcing
###
start_time = time.time()
# Hack to force datetimes to display in GMT/UTC (numpy 1.11.1 has fixed this but other dependent modules (pynio) can't handel numpy 1.11.1)
os.environ['TZ'] = 'GMT'
time.tzset()

# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) == 1:
    raise ValueError('requires one argument [configuration file] (i.e. python GRIB2_to_CHM_forcing.py forcing_config.py')

# Get name of configuration file/module
configfile = sys.argv[-1]

# Load in configuration file as module
X = imp.load_source('',configfile)

output_dt = 1 # Hours

# Assign to local variables
netcdf_dir = X.netcdf_dir
ascii_dir   = X.ascii_dir
Forcing_config_file = X.Forcing_config_file
lat_r = X.lat_r
lon_r = X.lon_r
var_dic = X.var_dic
local_time_offset = X.local_time_offset
coordsystem = X.coordsystem
if coordsystem=='pro':
    utm_zone = X.utm_zone

# Output dir
output_dir = ascii_dir + '_filled'
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Move to input
os.chdir(ascii_dir)

all_files = sorted(set(glob.glob('*.chm')))

def quick_fill(cf):
    cO = chm_forcing.point_forcing(cf, output_dir)
    cO.add_missing_timesteps(freq='H')
    cO.fill_missing_variables(method='linear')
    cO.write_to_ascii(cf)
    return(cf)

values = [delayed(quick_fill)(cf) for cf in all_files]
results = compute(*values, get=dask.multiprocessing.get)
print("--- Took %s minutes ---" % ((time.time() - start_time)/60))

# for cf in all_files:
#     print(cf)
#     cO = ascii_file(cf)
#     cO.add_missing_timesteps(freq='H')
#     cO.fill_missing_variables(method='linear')
#     cO.write_to_ascii(cf)

    # # Test Plot
    # plt.figure()
    # plt.plot(cO.df.index, cO.df['t'],'k*',linewidth=6)
    # plt.plot(cO.df_c.index, cO.df_c['t'], 'r')
    # plt.plot(cO.df_c.index, cO.df_c['t'], 'ob')
    #
    # plt.show()



