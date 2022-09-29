from osgeo import gdal,ogr,osr

import subprocess
import os
import shutil

def _gdal_prefix():
    try:
        prefix = subprocess.run(["gdal-config","--prefix"], stdout=subprocess.PIPE).stdout.decode()
        prefix = prefix.replace('\n', '')

        return prefix

    except FileNotFoundError as e:
        raise(""" ERROR: Could not find the system install of GDAL. 
                  Please install it via your package manage of choice.
                """
            )

def clip_no_data(settings, dem_filename ):

    gdal_prefix = os.path.join(_gdal_prefix(),'bin')+'/'
    user_output_dir = settings['snowcast_base']
    tmp_dir = 'tmp_clip'

    shutil.rmtree(os.path.join(user_output_dir,tmp_dir),ignore_errors=True)
    os.mkdir(os.path.join(user_output_dir, tmp_dir))


    # mask data values
    exec_str = """%sgdal_calc.py -A %s --outfile %s --NoDataValue 0 --overwrite --calc="1*(A>-100)" """ % (gdal_prefix,
        dem_filename,
        os.path.join(user_output_dir,tmp_dir,'calc.tif'))
    subprocess.check_call([exec_str],   shell=True)

    # convert to shp file
    exec_str = """%sgdal_polygonize.py -8 -b 1 -f "ESRI Shapefile" %s %s """ % (gdal_prefix,
        os.path.join(user_output_dir,tmp_dir,'calc.tif'),
        os.path.join(user_output_dir,tmp_dir))
    subprocess.check_call([exec_str],  shell=True)


    # get out input srs
    src_ds = gdal.Open(dem_filename)
    wkt_out = src_ds.GetProjection()
    srs_out = osr.SpatialReference()
    srs_out.ImportFromWkt(wkt_out)



    bufferDist = -0.1 #degrees

    outputBufferfn = os.path.join(user_output_dir,tmp_dir,'buffered_out.shp')

    print('Simplifying extents by buffer distance = ' + str(bufferDist))

    inputds = ogr.Open( os.path.join(user_output_dir,tmp_dir,'out.shp'))
    inputlyr = inputds.GetLayer()

    shpdriver = ogr.GetDriverByName('ESRI Shapefile')
    if os.path.exists(outputBufferfn):
        shpdriver.DeleteDataSource(outputBufferfn)
    outputBufferds = shpdriver.CreateDataSource(outputBufferfn)
    bufferlyr = outputBufferds.CreateLayer(outputBufferfn, srs_out, geom_type=ogr.wkbPolygon)
    featureDefn = bufferlyr.GetLayerDefn()

    for feature in inputlyr:
        ingeom = feature.GetGeometryRef()
        geomBuffer = ingeom.Buffer(bufferDist)

        outFeature = ogr.Feature(featureDefn)
        outFeature.SetGeometry(geomBuffer)
        bufferlyr.CreateFeature(outFeature)
        outFeature = None
    # close the files
    inputds = None
    outputBufferds = None


    exec_str = """%sogr2ogr %s -overwrite -simplify 0.1 %s """ % (gdal_prefix, 
        os.path.join(user_output_dir,tmp_dir,'out_simplify.shp'),
        outputBufferfn)
    subprocess.check_call([exec_str],  shell=True)


    exec_str = """%sgdalwarp -of GTiff -cutline %s -crop_to_cutline -dstalpha %s %s """ % (gdal_prefix,
                outputBufferfn, dem_filename, dem_filename+'_clipped.tif')
    subprocess.check_call([exec_str], shell=True)


    shutil.move(dem_filename,
        dem_filename+'.tmp')

    shutil.move(dem_filename+'_clipped.tif',
        dem_filename
        )

    os.remove(dem_filename+'.tmp')

    shutil.rmtree(os.path.join(user_output_dir,tmp_dir),ignore_errors=True)

    
def to_ascii(settings, in_filename, out_filename):

    gdal_prefix = os.path.join(_gdal_prefix(), 'bin')+'/'
    user_output_dir = settings['snowcast_base']

    exec_str = f"""{gdal_prefix}gdalwarp -tr 0.036 0.036 -t_srs EPSG:4326 {in_filename} tmp_{in_filename} """
    subprocess.check_call([exec_str], shell=True)

    # clip_no_data(settings, f'tmp_{in_filename}')

    exec_str = f"""{gdal_prefix}gdal_translate tmp_{in_filename} {out_filename} """
    subprocess.check_call([exec_str],  shell=True)

    os.remove(f'tmp_{in_filename}')

