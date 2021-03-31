# AB Env and Parks does not give easy access to their real time stations.
# They only provide the last few days of hourly data
# urls for files look like this:
# http://environment.alberta.ca/apps/Basins/data/text/snow/05CA805.csv

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import xarray as xr
import sys
import os
import imp
import wget
import seaborn as sns
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

# Stations we wish to download
sta_code = ['05AD803','13A19S','05AA809','05DB802','05BJ805','05BL811','13A27S','05BL812','05CA805','05AA817','05BB803','05BF824']
c_network = 'environmentAlberta'


# # Create paths

# In[ ]:

# Data network
network = 'AB_recent'

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
netcdf_file_out =  os.path.join(netcdf_dir,'AB_NRT.nc')

# Metadata for AB pillows 
meta_file         = 'AB_Station_Metadata.csv'
meta_file_path    = os.path.join(git_dir,'In_Situ_Data','metadata',meta_file)


# # Download Near-real time AB data (Updated hourly)

# In[ ]:

url_base = 'http://environment.alberta.ca/apps/Basins/data/text/snow/'
file_ext = '.csv'


# In[ ]:

os.chdir(download_dir)
Var_names = ['SWE','Snowdepth','AirTemperature','Precipitation']
AB_2_BC_var_dict = {'Snow Water Equivalent':Var_names[0],'Snow Depth':Var_names[1],'Air Temperature':Var_names[2]}
Var_units = ['mm','cm','C','mm']
unit_dict = dict(zip(Var_names,Var_units))


# In[ ]:

# Remove previous files
for cfile in sta_code:
    try:
        os.remove(cfile+file_ext)
    except OSError:
        pass


# In[ ]:

# Download newest files
for csta in sta_code:
    try:
        wget.download(url_base+csta+file_ext) 
    except OSError:
        pass


# In[ ]:

# Import each data variable
ds_list = []
sta_list_used = []
for (i,csta) in enumerate(sta_code):
    cf = csta+file_ext
    print(cf)
    
    # Load in to python
    df = pd.read_csv(cf,index_col=1, skiprows=20, skipfooter=1, engine='python', parse_dates=True)
    df.index.names = ['Time_MST']
    
    # Remove units
    df = df[1:]
    
    # Rename columns
    df = df.rename(columns = AB_2_BC_var_dict)
    
    # Drop Station No.
    df = df.drop('Station No.', 1)
    
    # Force to numeric
    df = df.convert_objects(convert_numeric=True)
    
    # df to ds
    ds_c = xr.Dataset.from_dataframe(df)
    # Add as coord
    ds_c['staID'] = csta
    ds_c.set_coords('staID',inplace=True)
    
    # Store as dict (if we have any data)
    if ds_c.Time_MST.size>0:
        ds_list.append(ds_c)
        sta_list_used.append(csta)


# In[ ]:




# In[ ]:




# In[ ]:

# Merge into netcdf
ds = xr.concat(ds_list,'staID')
ds


# In[ ]:

ds.staID


# In[ ]:

# Read in metadata provided by Stephen at AEP.DMNRT@gov.ab.ca
metadata = pd.read_csv(meta_file_path, index_col='stnnumber', encoding = "ISO-8859-1", usecols=['stnname','stnnumber','stnlatitude','stnlongitude','stnelevationmet'])
metadata.index.names = ['staID']


# In[ ]:

# Extract only stations we are interested in
metadata = metadata.loc[ds.staID.values]


# In[ ]:

## ADD UNITS
# Add variable attributes (units), and fix variable names (remove spaces)
for cvar in ds.data_vars:
    # add units as attributes
    ds.get(cvar).attrs['unit']   = unit_dict[cvar]


# In[ ]:

# ## Add station metadata
ds['station_name'] = xr.DataArray(metadata['stnname'],coords={'staID':metadata.index}, dims='staID')
ds['Lat'] = xr.DataArray(metadata['stnlatitude'],coords={'staID':metadata.index}, dims='staID')
ds['Lon'] = xr.DataArray(metadata['stnlongitude'],coords={'staID':metadata.index}, dims='staID')
ds['Elevation'] = xr.DataArray(metadata['stnelevationmet'],coords={'staID':metadata.index}, dims='staID')


# In[ ]:

ds.set_coords(['station_name','Lat','Lon','Elevation'], inplace=True)


# In[ ]:

#plt.plot(ds.Time_MST,ds.SWE.T.values);


# In[ ]:

#plt.plot(ds.Time_MST,ds.Snowdepth.T.values);


# In[ ]:

#plt.plot(ds.Time_MST,ds.AirTemperature.T.values);


# In[ ]:




# In[ ]:

# Adjust time zone to UTC
# ISSUE here is that time zone is "Current" as in it changes between MDT and MST (dumb), so go with MST here as we most often care about snow during witner
# MST to UTC (-7 hours)
ds['Time_MST'] = ds.Time_MST + np.timedelta64(-7,'h')
ds.rename({'Time_MST':'Time_UTC'},inplace=True)


# In[ ]:

# Add Netowork
ds.coords['network'] = xr.DataArray([c_network for x in ds.staID], dims='staID')


# In[ ]:

# Save as netcdf file
ds.to_netcdf(netcdf_file_out)


# In[ ]:




# In[ ]:



