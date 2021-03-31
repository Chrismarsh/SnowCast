# Import the Earth Engine Python Package
import ee
try:
    import urllib.request as urllib2
except ImportError:
    import urllib2
import os
import sys
import math
import shutil
import zipfile
import glob
import subprocess

# TODO:
# 1) Add save of current files in pickel file, and option to check if alredy have it and skip
# 2) Add Modies

# TODO: Classification issues
# Soil as cloud (at snow line)
# Cloud in general
# Cloud height

# Initialize the Earth Engine object, using the authentication credentials.
ee.Initialize()

# Make geometery

# Fortress
# output_extent = ee.Geometry.Polygon(
#         [[[-115.49652099609375, 50.66977366293606],
#           [-114.98016357421875, 50.66281013238712],
#           [-114.99114990234375, 50.96131001015316],
#           [-115.47454833984375, 50.95785003925093]]])

# CRHO (crho_extent.tif)
output_extent = ee.Geometry.Polygon(
        [[[-116.645, 50.66],
          [-114.769166666667, 50.66],
          [-114.769166666667, 51.7933333333333],
          [-116.645, 51.7933333333333]]])

#output_extent = ee.Geometry.Polygon(
#        [[[-121.248, 46.455],
#          [-120.441, 46.455],
#          [-120.441, 46.814],
#          [-121.248, 46.814]]])

# Output dir
# output_dir = r'F:\Work\e\Data\GEE\Test_assimilation'
output_dir = r'/media/data2/nicway/Remote/GEE_Snowcover_assimilation'
#output_dir = r'/media/data2/nicway/Remote/Yakima'


# 2) Select date period of interest.
date_start = '2017-09-01'
#date_start = '2017-09-22'
date_end   = '9999-09-05'
# date_start = '2017-02-01'
# date_end   = '2017-04-01'

# 3) Specify method parameters (default values are given below)
max_cloudy_percent  = 30 # Maximum cloud cover in a given tile to be considered (suggest 30)
max_tree_cover      = 30 # Max tree cover to allow, greater values are masked (suggest 30)
min_water_occurance = 70 # Minimum percent water cover to classfiy as masked, valuese greater are masked as water (suggest 70)
Missing_Val = 6 # Custom classification has 6 as missing value
# Landsat 8 Parameters
output_res_LS8      = 30 # m
Cloud_threshold     = 80 # L8 cloud detection, Found through trial and error that this
# value works best over mountains.
# Sentinel-2 Parameters
output_res_S2       = 20 # m

# Define functions

def downloadZip(url):
  u = urllib2.urlopen(url)
  meta = u.info()

  # A zip download
  zipped_file = (meta.getheaders("Content-disposition")[0]).replace('attachment; filename=', '')
  f = open(zipped_file, 'wb')
  print("Downloading: %s " % (zipped_file))
  # os.system('cls')
  file_size_dl = 0
  block_sz = 8192
  while True:
      buffer = u.read(block_sz)
      if not buffer:
          break

      file_size_dl += len(buffer)
      f.write(buffer)
      # status = r"%10d  " % (file_size_dl)
      # status = status + chr(8) * (len(status) + 1)
      # print(status)

  f.close()

  # Unzip and remove zipped file
  with zipfile.ZipFile(zipped_file) as zip_file:
      for member in zip_file.namelist():
          filename = os.path.basename(member)
          # skip directories
          if not filename:
              continue
          # copy file
          source = zip_file.open(member)
          target = open(os.path.join(output_dir, filename), "wb")
          with source, target:
              shutil.copyfileobj(source, target)
  # Remove zipped file
  os.remove(zipped_file)

  return target



# Load or import the Hansen et al. forest change dataset.
hansenImage = ee.Image('UMD/hansen/global_forest_change_2015_v1_3')
# Select the land/water mask.
treecover2000 = hansenImage.select('treecover2000')
forest_mask = treecover2000.gt(max_tree_cover) #.rename('treecover2000','forest') #.clip(output_extent)

# DEM for terrain shading
srtmDem = ee.Image("USGS/SRTMGL1_003") # 30m, better resolves topo, some artifacts
testDem = srtmDem #.clip(output_extent) 

# water mask
water = ee.Image('JRC/GSW1_0/GlobalSurfaceWater').select('occurrence')
water_mask = water.gt(min_water_occurance).rename(['water']) # Water was present greater than 70% of 1984-2015

# LANDSAT8
L8 = ee.ImageCollection('LANDSAT/LC08/C01/T1_RT_TOA')\
    .filterDate(date_start, date_end)\
    .filterBounds(output_extent)\
    .filter(ee.Filter.lt('CLOUD_COVER', max_cloudy_percent))

images_L8 = L8.getInfo()['features']
urls_L8 = []

# Check we found any images
if images_L8:
    # raise ValueError("No Images found for given date range and parameter settings.")

    # loop over images and get url for download
    for i in images_L8:
      assetId = i['id']
      c_image = ee.Image(assetId)
      imageLabel = assetId.split('/')[-1]
      print(imageLabel)

    # # Functions to classify landsat and sentinel images
    # def L8_classify(c_image):

      # Get bands we need
      vir = c_image.select('B3')
      swir = c_image.select('B6')

      # Cloud classification
      scored = ee.Algorithms.Landsat.simpleCloudScore(c_image)
      cloudmask = scored.select(['cloud']).gte(Cloud_threshold).rename(['cloud'])

      # Cloud shadow estimation
      cloud2 = cloudmask #.focal_max(10)
      azimuth = ee.Number(c_image.get('SUN_AZIMUTH')).multiply(math.pi / 180.0).add(0.5 * math.pi)
      x = azimuth.cos().multiply(10).round()
      y = azimuth.sin().multiply(10).round()
      offset = ee.Number(5) # this should depend on zenith / cloud height
      shadow = cloud2.changeProj(cloud2.projection(), cloud2.projection().translate(x.multiply(offset), y.multiply(offset)))
      shadow = shadow.gt(0).rename(['shadow'])

      # Terrain shading
      #solar position
      solarAzimuth = ee.Number(c_image.get('SUN_AZIMUTH'))

      #shadow from surrounding terrain
      zenith =  ee.Number(90).subtract(ee.Number(c_image.get('SUN_ELEVATION')))
      neighborhoodSize  = 200 # pixels
      terrainShadow = ee.Terrain.hillShadow(testDem,solarAzimuth,zenith,neighborhoodSize,False)
      terrainShadow = terrainShadow.reproject(testDem.projection()).rename(['terrainShadow'])

      # Calculate ndsi
      image_ndsi = vir.subtract(swir).divide(vir.add(swir)).rename(['NDSI'])

      # Output custom classification
      #  1 snow        2 soil      3 forest       4 cloud shadow 5 cloud  6 missing 7 terrain shadow 8 water
      img_class1 = image_ndsi.expression("b('NDSI')>0.4 ? 1 : 2").rename(['classification'])
      img_class2 = img_class1.addBands(forest_mask).expression("b('treecover2000')==1 ? 3 : b('classification')")
      img_class3 = img_class2.addBands(water_mask).expression("b('water')==1 ? 8 : b('classification')")
      img_class4 = img_class3.addBands(terrainShadow).expression("b('terrainShadow')==0 ? 7 : b('classification')")
      img_class5 = img_class4.addBands(shadow).expression("b('shadow')==1 ? 4 : b('classification')")
      img_classified = img_class5.addBands(cloudmask).expression("b('cloud')==1 ? 5 : b('classification')")
      # Hack way to mask to original extent of input raw data
      img_classified = img_classified.addBands(vir.mask()).expression("b('B3')==0 ? 6 : b('classification')")
      # (Optional) add in few bands to visualize
      img_classified = img_classified.addBands(c_image.select('B5', 'B4', 'B3'))

      urls_L8.append(img_classified.getDownloadUrl({'name': imageLabel + '_classified', 'scale':
          output_res_LS8, 'region': output_extent.toGeoJSONString(),'filePerBand': False}))

    # Move to donwload dir
    os.chdir(output_dir)

    # Commented out below to test S2
    # Use function downloadZip for each URL created
    for u in urls_L8:
      # print(u)
      tmepF = downloadZip(u)

    # Remove annoying tfw files
    [os.remove(cf) for cf in glob.glob('*.tfw*')]

    # Find same day images on different tiles and merge
    prefix = 'LC08'
    # First remove any *merged* existing tifs
    mrg_files = glob.glob('*merged*.tif')
    [os.remove(cf) for cf in mrg_files]
    # Get unique dates
    for file in glob.glob(prefix+'*classified.tif'):
        print(file)
        cdate = file.split('_')[2].split('.')[0]
        # Find other files with same date
        sim_files = glob.glob(prefix+'*'+cdate+'*classified.tif')
        if len(sim_files) > 1: # Found at least 2
            # Call gdal merge to combine files
            merged_tif_file = prefix+'_merged_'+cdate+'.tif'
            #gdal_merge_path = r'C:\Users\new356\Anaconda2\pkgs\gdal-2.2.1-np111py27_vc9_0\Lib\site-packages\GDAL-2.2.1-py2.7-win32.egg-info\scripts\gdal_merge.py'
            # gdal_merge_path = 'gdal_merge.py'
            merge_command = ['','-o', merged_tif_file] + sim_files # Need blank first arg because gdal_merge.py starts at arg 1
            # print(merge_command)

            print("Merging to file ", merged_tif_file, sim_files)


            subprocess.check_call(" ".join(['gdalbuildvrt', '-srcnodata', str(Missing_Val), 'temp.vrt'] + sim_files), shell=True)
            subprocess.check_call(" ".join(['gdal_translate', 'temp.vrt', merged_tif_file]), shell=True)
            os.remove('temp.vrt') # Clean up

            # # gdal_merge.py method (doesn't work, can't not fill nan pixels)
            # sys.argv = merge_command
            # gm.main()

            # Remove indiv files
            [os.remove(cf) for cf in sim_files]






#################################################
# Sentinel-2
#################################################

# Sentinel-2
S2 = ee.ImageCollection('COPERNICUS/S2')\
    .filterDate(date_start, date_end)\
    .filterBounds(output_extent)\
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloudy_percent))


images_S2 = S2.getInfo()['features']
urls_S2 = []

# Check we found any images
if images_S2:
    # raise ValueError("No S2 Images found for given date range and parameter settings.")

    # loop over images and get url for download
    for i in images_S2:
      assetId = i['id']
      c_image = ee.Image(assetId)
      imageLabel = assetId.split('/')[-1]
      print(imageLabel)

    # S2_classify = function(c_image) {
      # Get bands we need
      vir = c_image.select('B3')
      swir = c_image.select('B11')

      # # 1) Sentinel default cloud mask
      # # Opaque and cirrus cloud masks cause bits 10 and 11 in QA60 to be set,
      # # so values less than 1024 are cloud-free
      QA60 = c_image.select('QA60')
      QA20r = QA60.resample().rename(['cloud'])
      cloudmask = QA20r.gte(1024)
      # # QA20r = QA20r.expression("b('cloud')!=0 ? 1 : 0")

      # 2) Cloud classification using Landsat method (does not work because S2 missing thermal bands)
      # L8_img = c_image.select(S2_BANDS, L8_BANDS)
      # L8_img = L8_img.set('SENSOR_ID', 'OLI_TIRS')
      # scored = ee.Algorithms.Landsat.simpleCloudScore(L8_img)
      # cloudmask = scored.select(['cloud']).gte(Cloud_threshold).rename(['cloud'])

      # 3) Cloud mapping from Simon
      # score = cloudScore(c_image)
      # cloudmask = score.g

      # Cloud shadow estimation
      cloud2 = cloudmask #.focal_max(10)
      azimuth = ee.Number(c_image.get('MEAN_SOLAR_AZIMUTH_ANGLE')).multiply(math.pi / 180.0).add(0.5 * math.pi)
      x = azimuth.cos().multiply(10).round()
      y = azimuth.sin().multiply(10).round()
      offset = ee.Number(5) # this should depend on zenith / cloud height
      shadow = cloud2.changeProj(cloud2.projection(), cloud2.projection().translate(x.multiply(offset), y.multiply(offset)))
      shadow = shadow.gt(0).rename(['shadow'])

      # Terrain shading
      #solar position
      solarAzimuth = ee.Number(c_image.get('MEAN_SOLAR_AZIMUTH_ANGLE'))

      #shadow from surrounding terrain
      zenith =  ee.Number(c_image.get('MEAN_SOLAR_ZENITH_ANGLE'))
      neighborhoodSize  = 200 # Pixels
      terrainShadow=ee.Terrain.hillShadow(testDem,solarAzimuth,zenith,neighborhoodSize,False)
      terrainShadow = terrainShadow.reproject(testDem.projection()).rename(['terrainShadow'])

      # Calculate ndsi
      image_ndsi = vir.subtract(swir).divide(vir.add(swir)).rename(['NDSI'])

      #  1 snow        2 soil      3 forest       4 cloud shadow 5 cloud  6 missing 7 terrain shadow
      img_class1 = image_ndsi.expression("b('NDSI')>0.4 ? 1 : 2").rename(['classification'])
      img_class2 = img_class1.addBands(forest_mask).expression("b('treecover2000')==1 ? 3 : b('classification')")
      img_class3 = img_class2.addBands(water_mask).expression("b('water')==1 ? 8 : b('classification')")
      img_class4 = img_class3.addBands(terrainShadow).expression("b('terrainShadow')==0 ? 7 : b('classification')")
      img_class5 = img_class4.addBands(shadow).expression("b('shadow')==1 ? 4 : b('classification')")

      img_classified = img_class5.addBands(cloudmask).expression("b('cloud')==1 ? 5 : b('classification')")
      # Hack way to mask to original extent of input raw data
      img_classified = img_classified.addBands(vir.mask()).expression("b('B3')==0 ? 6 : b('classification')")
      # (Optional) add in few bands to visualize
      img_classified = img_classified.addBands(c_image.select('B5', 'B4', 'B3'))

      urls_S2.append(img_classified.getDownloadUrl({'name': imageLabel + '_classified', 'scale':
          output_res_S2, 'region': output_extent.toGeoJSONString(), 'filePerBand': False}))


    # Move to donwload dir
    os.chdir(output_dir)

    # Use function downloadZip for each URL created
    S2_files = []
    for u in urls_S2:
      # print(u)
      S2_files.append(downloadZip(u))

    # Remove annoying tfw files
    [os.remove(cf) for cf in glob.glob('*.tfw*')]

    # Find same day images on different tiles and merge
    prefix = 'S2'
    # First remove any *merged* existing tifs
    #mrg_files = glob.glob('*merged*.tif')
    #[os.remove(cf) for cf in mrg_files]
    # Get unique dates
    for file in S2_files: #glob.glob(prefix+'*classified.tif'):
        print(os.path.basename(str(file.name)))
        cdate = os.path.basename(str(file.name)).split('_')[0]
        # Find other files with same date
        sim_files = glob.glob(cdate+'*classified.tif')
        if len(sim_files) > 1: # Found at least 2
            # Call gdal merge to combine files
            merged_tif_file = prefix+'_merged_'+cdate+'.tif'
            #gdal_merge_path = r'C:\Users\new356\Anaconda2\pkgs\gdal-2.2.1-np111py27_vc9_0\Lib\site-packages\GDAL-2.2.1-py2.7-win32.egg-info\scripts\gdal_merge.py'
            # gdal_merge_path = 'gdal_merge.py'
            merge_command = ['','-o', merged_tif_file] + sim_files # Need blank first arg because gdal_merge.py starts at arg 1
            # print(merge_command)

            print("Merging to file ", merged_tif_file, sim_files)

            subprocess.check_call(" ".join(['gdalbuildvrt', '-srcnodata', str(Missing_Val), 'temp.vrt'] + sim_files), shell=True)
            subprocess.check_call(" ".join(['gdal_translate', 'temp.vrt', merged_tif_file]), shell=True)
            os.remove('temp.vrt') # Clean up

            # Remove indiv files
            [os.remove(cf) for cf in sim_files]

