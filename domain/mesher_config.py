
dem_filename='windmapper_config/ref-DEM-utm.tif'

max_area=5000**2
max_tolerance=50
min_area=50**2

lloyd_itr = 1
do_smoothing = True
max_smooth_iter = 1
smoothing_scaling_factor = 1

simplify=False
simplify_tol=100
simplify_buffer=-50
write_shp=False
write_vtu=True

use_input_prj = False
wkt_out = "PROJCS[\"North_America_Albers_Equal_Area_Conic\"," \
              "     GEOGCS[\"GCS_North_American_1983\"," \
              "         DATUM[\"North_American_Datum_1983\"," \
              "             SPHEROID[\"GRS_1980\",6378137,298.257222101]]," \
              "         PRIMEM[\"Greenwich\",0]," \
              "         UNIT[\"Degree\",0.017453292519943295]]," \
              "     PROJECTION[\"Albers_Conic_Equal_Area\"]," \
              "     PARAMETER[\"False_Easting\",0]," \
              "     PARAMETER[\"False_Northing\",0]," \
              "     PARAMETER[\"longitude_of_center\",-96]," \
              "     PARAMETER[\"Standard_Parallel_1\",20]," \
              "     PARAMETER[\"Standard_Parallel_2\",60]," \
              "     PARAMETER[\"latitude_of_center\",40]," \
              "     UNIT[\"Meter\",1]," \
              "     AUTHORITY[\"EPSG\",\"102008\"]]" 
              
parameter_files = {  'Ninja2_U' : {'file':'/Users/chris/Documents/science/code/SnowCast/v2/0_domain/windmapper_config/ref-DEM-utm_0_U.vrt','method':'mean'}, 
'Ninja2_V' : {'file':'/Users/chris/Documents/science/code/SnowCast/v2/0_domain/windmapper_config/ref-DEM-utm_0_V.vrt','method':'mean'}, 
'Ninja2' : {'file':'/Users/chris/Documents/science/code/SnowCast/v2/0_domain/windmapper_config/ref-DEM-utm_0_spd_up_1000.vrt','method':'mean'}, 
'Ninja1_U' : {'file':'/Users/chris/Documents/science/code/SnowCast/v2/0_domain/windmapper_config/ref-DEM-utm_180_U.vrt','method':'mean'}, 
'Ninja1_V' : {'file':'/Users/chris/Documents/science/code/SnowCast/v2/0_domain/windmapper_config/ref-DEM-utm_180_V.vrt','method':'mean'}, 
'Ninja1' : {'file':'/Users/chris/Documents/science/code/SnowCast/v2/0_domain/windmapper_config/ref-DEM-utm_180_spd_up_1000.vrt','method':'mean'} }
              