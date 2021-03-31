import glob
import imp
import os
import pandas as pd
import sys
import xarray as xr
from datetime import datetime

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

# Data network
network = 'EC_Snow_Courses'

# Location to download historical AB station data
download_dir = os.path.join(data_dir,network,'current')
# Make if does not exist
if not os.path.exists(download_dir):
    os.makedirs(download_dir)
    
# Netcdf file to save to
netcdf_dir   = os.path.join(data_dir,network,'netcdf')
# Make if does not exist
if not os.path.exists(netcdf_dir):
    os.makedirs(netcdf_dir)
netcdf_file_out =  os.path.join(netcdf_dir,'EC_Snow_Courses.nc')

# # Metadata for AB pillows 
meta_file         = 'ABE_AGG_Station_Metadata.csv'
meta_file_path    = os.path.join(git_dir,'In_Situ_Data','metadata',meta_file)


# In[ ]:

os.chdir(download_dir)


# In[ ]:

vars_in = {'SD-SS':'SnowDepth_point','SW-SS':'SWE_point'}
unit_dict = {'SnowDepth_point':'m','SWE_point':'m'}
parse = lambda x: datetime.strptime(x, '%Y%m%d %H%M%S')


# In[ ]:

var_temp = []
for cvar in vars_in.keys():
    # Get list of files
    c_files = glob.glob('*'+cvar+'*.csv')
    
    da_temp = []
    # Loop through files
    for cf in c_files:
#         print(cf)
        # Load into a dataframe
        df_dat = pd.read_csv(cf,index_col=0, skiprows=15, engine='python', parse_dates = [['Date', 'Time']])
        df_dat = df_dat.convert_objects(convert_numeric=True) # Force to floats
        df_dat.index.name = 'Time_UTC'
        
        df_hdr_raw = pd.read_csv(cf, nrows=14)

        # Clean up messy header info
        df_hdr = df_hdr_raw.copy()
        for i2, row in df_hdr_raw.iterrows():
            df_hdr.loc[i2] = row.str.split(r'\t').str[1]
            
        # Get info
        cstaID = df_hdr.iloc[1].item()
        csta_lat = float(df_hdr.iloc[13].item())
        csta_lon = float(df_hdr.iloc[12].item())
        csta_name = df_hdr.iloc[0].item()
        
        # Drop rows with bad times (NAT)
        df_dat = df_dat[pd.notnull(df_dat.index)]
        
        # Convert to Da
        da = xr.DataArray.from_series(df_dat.iloc[:, 0]) # coords={'Time_UTC':df_dat.index, 'staID':cstaID}, dims=('Time_UTC','staID'))
        da.name = vars_in[cvar]
        da.coords['staID'] = cstaID
        da.coords['Lat'] = csta_lat
        da.coords['Lon'] = csta_lon
        da.coords['station_name'] = csta_name
        
        #Store
        da_temp.append(da)
    
    # Combine all stations
    ds_cvar = xr.concat(da_temp, dim='staID')
    var_temp.append(ds_cvar)
    
# Merge
ds_out = xr.merge(var_temp)


# In[ ]:




# In[ ]:




# In[ ]:

# Units to standard
ds_out['SWE_point'] = ds_out['SWE_point'] / 1000 # mm to m
ds_out['SnowDepth_point'] = ds_out['SnowDepth_point'] / 100 # cm to m


# In[ ]:

## ADD UNITS
# Add variable attributes (units), and fix variable names (remove spaces)
for cvar in ds_out.data_vars:
    # add units as attributes
    ds_out.get(cvar).attrs['unit'] = unit_dict[cvar]


# In[ ]:

# Orig filese are missing Elevation, so used a separate metadata file
# Import metadata for each station
metadata_EL = pd.read_csv(meta_file_path,index_col='staID',delimiter=',',na_values=[0])
metadata_EL = metadata_EL.loc[ds_out.staID.values]
ds_out.coords['Elevation'] = xr.DataArray(metadata_EL['Elevation'],coords={'staID':metadata_EL.index}, dims='staID')


# In[ ]:

# Add Network(s)
ds_out.coords['network'] = xr.DataArray([network for x in ds_out.staID], dims='staID')


# In[ ]:

ds_out


# In[ ]:

# Save as netcdf file
ds_out.to_netcdf(netcdf_file_out)
print("saved")


# In[ ]:

# Quick Plot
#for cvar in ds_out.data_vars:
#    plt.figure()
#    for csta in ds_out.staID:
#        plt.scatter(ds_out.Time_UTC.values, ds_out[cvar].sel(staID=csta).values)


# In[ ]:




# In[ ]:




# In[ ]:



