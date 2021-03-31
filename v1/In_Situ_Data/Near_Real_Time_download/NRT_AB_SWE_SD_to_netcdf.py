import imp
import matplotlib.pyplot as plt
import numpy as np
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

# In[ ]:

# Stations we wish to download
sta_code = ['2A21P','05DD804','1A01P','1A17P','1A14P','07BB811','07BB814','05AD803','13A19S','05AA809','05DB802','05BJ805','05BL811','13A27S','05BL812','05CA805','05AA817','05BB803','05BF824']
# Variables we want to download (currently only SW (SWE) and SD (Snow depth))
variables = ['SW','SD']
c_network = 'environmentAlberta'


# # Create paths

# In[ ]:

# Data network
network = 'AB_POR'

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
netcdf_file_out =  os.path.join(netcdf_dir,'AB_SWE_SD_NRT.nc')

# Metadata for AB pillows 
meta_file         = 'AB_Station_Metadata.csv'
meta_file_path    = os.path.join(git_dir,'In_Situ_Data','metadata',meta_file)


# # Download AB pillow SWE and SD data, Period-of-record to last midnight

# In[ ]:

#  example: https://environment.alberta.ca/apps/Basins/data/porExtracts/porExtract_AB_05BB803_SW_Cmd.Cor-Seas.C.csv
url_base  = 'https://environment.alberta.ca/apps/Basins/data/porExtracts/'
file_base = 'porExtract_AB_'
file_ext = '_Cmd.Cor-Seas.C.csv'


# In[ ]:

os.chdir(download_dir)
Var_names = ['SWE','Snowdepth','AirTemperature','Precipitation']
AB_2_BC_var_dict = {'Value(mm)':Var_names[0],'Value(cm)':Var_names[1]}
Var_units = ['mm','cm','C','mm']
unit_dict = dict(zip(Var_names,Var_units))


# In[ ]:

# Remove previous files
for cvar in variables:
    for cfile in sta_code:
        try:
            os.remove(file_base+cfile+'_'+cvar+file_ext)
        except OSError:
            pass


# In[ ]:

# Download newest files
for cvar in variables:
    for csta in sta_code:
        cfile = url_base+file_base+csta+'_'+cvar+file_ext
        print('\r')
        try:
            wget.download(cfile) 
        except OSError:
            print("Could not download "+cvar+" for "+csta)
            pass


# In[ ]:

# Import files
ds_var_list = []
for cvar in variables:
    ds_list = []
#     sta_list_used = []
    for (i,csta) in enumerate(sta_code):
        cf = file_base+csta+'_'+cvar+file_ext
        if os.path.isfile(cf):
            print(cf)

            # Load in to python
            dateparse = lambda x: pd.datetime.strptime(x, '%Y-%m-%d %H:%M:%S')
            try: # Because sometimes the file exists, but is empty
                df = pd.read_csv(cf,index_col=0, skiprows=23, engine='python', parse_dates={'datetime': ['Date', 'Time']}, date_parser=dateparse)
            except:
                print("Could not parse "+cf+". Something wrong with file format.")
                continue
            df.index.names = ['Time_MST']

            # Rename columns
            df = df.rename(columns = AB_2_BC_var_dict)

            # df to ds
            ds_c = xr.Dataset.from_dataframe(df)
            # Add as coord
            ds_c['staID'] = csta
            ds_c.set_coords('staID',inplace=True)

            # Store as dict (if we have any data)
            if ds_c.Time_MST.size>0:
                ds_list.append(ds_c)
#                 sta_list_used.append(csta)

    # Concat all stations for one variable into netcdf
    ds_var = xr.concat(ds_list,'staID')
    ds_var_list.append(ds_var)


# In[ ]:




# In[ ]:

# Merge ds of different variables together
ds = xr.merge(ds_var_list)
ds


# In[ ]:

## ADD UNITS
# Add variable attributes (units), and fix variable names (remove spaces)
for cvar in ds.data_vars:
    # add units as attributes
    ds.get(cvar).attrs['unit']   = unit_dict[cvar]


# In[ ]:




# In[ ]:

# Read in metadata provided by Stephen at AEP.DMNRT@gov.ab.ca
metadata = pd.read_csv(meta_file_path, index_col='stnnumber', encoding = "ISO-8859-1", usecols=['stnname','stnnumber','stnlatitude','stnlongitude','stnelevationmet'])
metadata.index.names = ['staID']


# In[ ]:




# In[ ]:

# Extract only stations we are interested in
metadata = metadata.loc[ds.staID.values]


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

# Adjust time zone to UTC
# MST to UTC (-7 hours)
ds['Time_MST'] = ds.Time_MST + np.timedelta64(-7,'h')
ds.rename({'Time_MST':'Time_UTC'},inplace=True)


# In[ ]:

# Add Netowork
ds.coords['network'] = xr.DataArray([c_network for x in ds.staID], dims='staID')


# In[ ]:

# Reindex to have continous time steps
Time_UTC_new = np.arange(ds.Time_UTC.values[0], ds.Time_UTC.values[-1], dtype='datetime64[h]')
ds_fill = ds.reindex({'Time_UTC':Time_UTC_new})


# In[ ]:

# Save as netcdf file
ds_fill.to_netcdf(netcdf_file_out)


# In[ ]:



