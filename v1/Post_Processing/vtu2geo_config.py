# Configuration file for vtu2geo tool

# Vtu base name (i.e. base_name_XXX.vtu)
base = 'SC'

# Input path to where output vtu files are located
input_path = '/home/nwayand/snow_models/output_CHM/SnowCast/forecast_CRHO_spinup/meshes/SC.pvd'
output_path = '/home/nwayand/snow_models/output_CHM/SnowCast/KML_files/'
config_dir = '/home/nwayand/snow_models/output_CHM/SnowCast/vtu_config'

user_define_extent = False

# Output variables
variables = ['snowdepthavg']  #set to None to dump all variables
var_resample_method    = {'snowdepthavg':'average'} # Methods to use when calculating clipped raster

# Output parameters
parameters = ['Elevation'] # paramters are one offs we want to extract from the vtu files
param_resample_method    = {'Elevation':'average'} # Methods to use when calculating clipped raster


# Output pixel size that the mesh is interpolated to (?)
pixel_size = 100 # (m)

