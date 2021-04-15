
# Configuration file for windmapper when a DEM is downloaded from the SRTM 30m archive

# Resolution of WindNinja simulations (in m)
res_wind = 150

# Number of wind speed categories (every 360/ncat degrees)
ncat = 8

# Flag to use existing DEM (DEM must be in UTM for WindNinja)
use_existing_dem = False

# If an existing DEM is not provided, the bounding box in lat lon must be provided
# Example for a region in the Jura, France
lat_min = 50.660000
lat_max = 51.793333
lon_min = -116.645000
lon_max = -114.769167

# Averaging method to compute the transfer function in the downscaling method
#       "mean_tile": the wind speed is average over the whole domain for each WN simulation (as in marsh et al, 2020)
#        "grid": the wind speed is averaged over a squared area of size targer_res (as in Vionnet et al., 2020) 
wind_average = 'grid'

# Target resolution for avegaging (in m)
targ_res = 1000

