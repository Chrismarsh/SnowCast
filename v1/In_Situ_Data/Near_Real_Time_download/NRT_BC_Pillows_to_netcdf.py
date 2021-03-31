import imp
import os
import pandas as pd
import seaborn as sns
import sys
import wget
import xarray as xr

sns.set_context("talk",font_scale=1.5)
sns.set_style('whitegrid')
# Load in config file
#######  load user configurable paramters here    #######
# Check user defined configuraiton file
if len(sys.argv) == 1:
    raise ValueError('Requires one argument [configuration file]')

# Get name of configuration file/module
configfile = sys.argv[-1]

# Load in configuration file as module
X = imp.load_source('',configfile)

# Assign to local variables
data_dir = X.data_dir
git_dir   = X.git_dir

# # Create paths

# In[ ]:

# Data network
network = 'BC_NRT'

# Location to download current AB station data
download_dir = os.path.join(data_dir,network,'current')
# Make if does not exist
if not os.path.exists(download_dir):
    os.makedirs(download_dir)
    
# Netcdf file to save to
netcdf_dir   = os.path.join(data_dir,network,'netcdf')
# Make if does not exist
if not os.path.exists(netcdf_dir):
    os.makedirs(netcdf_dir)
netcdf_file_out =  os.path.join(netcdf_dir,'BC_NRT.nc')

# Metadata for AB pillows 
meta_file         = 'BC_Station_Metadata.csv'
meta_file_path    = os.path.join(git_dir,'In_Situ_Data','metadata',meta_file)


# # Download Near-real time BC data (Updated hourly)

# In[ ]:

os.chdir(download_dir)
BC_files = ['SW.csv','SD.csv','TA.csv','PC.csv']
Var_names = ['SWE','Snowdepth','AirTemperature','Precipitation']
Var_units = ['mm','cm','C','mm']
c_network = 'bcRiverForecastCenter'


# In[ ]:

# Remove previous files
for cfile in BC_files:
    try:
        os.remove(cfile)
    except OSError:
        pass


# In[ ]:

# Download newest files
url_base         = 'http://bcrfc.env.gov.bc.ca/data/asp/realtime/data/'
[wget.download(url_base+cfile) for cfile in BC_files]


# In[ ]:

# Import metadata for each station
metadata = pd.read_csv(meta_file_path,index_col=1,delimiter=',',encoding='utf-8')


# In[ ]:

# Import each data variable
ds_dict   = {}
unit_dict = {}
for (i,cf) in enumerate(BC_files):
    print(cf)
    
    # Load in to python
    df = pd.read_csv(cf,index_col=0, skipfooter=1, engine='python', parse_dates=True)
    var_name_full  = Var_names[i]
    var_units = Var_units[i]
    df.index.names = ['Time_UTC']
    
    # Check for error in PC.csv
    if cf=='PC.csv':
        print('fixing Muskwa-Kechik error')
        df = df.rename(columns = {'4A34P Muskwa-Kechika':'4A34P Dowling Creek'})

    # Store as dict
    ds_dict[var_name_full] = df
    unit_dict[var_name_full] = var_units


# In[ ]:

# Merge into netcdf
ds = xr.Dataset(ds_dict)
ds.rename({'dim_1':'staID'},inplace=True) # rename time
ds['staID']        = [str(x).split(' ')[0] for x in ds.staID.values]


# In[ ]:




# In[ ]:

## ADD UNITS
# Add variable attributes (units), and fix variable names (remove spaces)
for cvar in ds.data_vars:
    # add units as attributes
    ds.get(cvar).attrs['unit']   = unit_dict[cvar]


# In[ ]:

## Add station metadata
ds['station_name'] = xr.DataArray(metadata['station'],coords={'staID':metadata.index}, dims='staID')
ds['Lat'] = xr.DataArray(metadata['latitude'],coords={'staID':metadata.index}, dims='staID')
ds['Lon'] = xr.DataArray(metadata['longitude'],coords={'staID':metadata.index}, dims='staID')
ds['Elevation'] = xr.DataArray(metadata['elevation'],coords={'staID':metadata.index}, dims='staID')


# In[ ]:

# Move to coords
ds.set_coords(['station_name','Lat','Lon','Elevation'],inplace=True)
ds


# In[ ]:

ds = ds.T
ds


# In[ ]:

ds.SWE.values


# In[ ]:




# In[ ]:




# In[ ]:




# In[ ]:




# In[ ]:

# Add Network
ds.coords['network'] = xr.DataArray([c_network for x in ds.staID], dims='staID')


# In[ ]:




# In[ ]:

# Save as netcdf file
ds.to_netcdf(netcdf_file_out)


# In[ ]:




# In[ ]:



