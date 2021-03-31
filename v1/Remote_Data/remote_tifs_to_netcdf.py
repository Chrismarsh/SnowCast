import datetime
import glob
import os
import xarray as xr

# Also requires rasterio

# Dir to vtu files
remote_files = os.path.normpath(r'/media/data2/nicway/Remote/GEE_Snowcover_assimilation')
nc_file_out = os.path.join(remote_files, 'GEE_Remote_current.nc')

# For each remote snowcover obs we have
r_files = glob.glob(os.path.join(remote_files, '*.tif'))
# print(r_files)
# TODO: hardcoded landsat over pass time, need to encode into geotif from GEE
def parse_date_LS8(file_in): # Local times
    return datetime.datetime.strptime(os.path.basename(file_in).split('_')[2].split(".")[0] + "12", '%Y%m%d%H')
r_dates = [parse_date_LS8(f) for f in r_files]
r_dict = dict(zip(r_dates, r_files))

# For each remote snowcover image over our domain
da_list = []
for c_r_date in sorted(r_dict.keys()):
    # Load in with rasterio/xarray
    da_r = xr.open_rasterio(r_dict[c_r_date]).sel(band=1).drop('band')
    da_r.coords['TIME_PST'] = c_r_date
    da_r.name = "SnowClassifcation"
    da_list.append(da_r)
ds = xr.concat(da_list,dim='TIME_PST')

ds.to_netcdf(nc_file_out)

print("Finished compiling GEE remote images into Netcdf file.")