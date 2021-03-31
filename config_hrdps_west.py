settings = dict()

import slack_webhook

settings['webhook_url'] = slack_webhook.webhook_url

################################################
# Paths
################################################
# Dir to put GEM grib2 files
settings['grib_dir'] = '/Users/chris/Documents/science/code/SnowCast/v2/nwp_forcing/grib_download'

# were to copy after we have processed. Not used, just kept "in case"
settings['grib_ar_dir'] = '/Users/chris/Documents/science/code/SnowCast/v2/nwp_forcing/grib_ar'

# Dir where output netcdf files go
settings['nc_ar_dir'] = '/Users/chris/Documents/science/code/SnowCast/v2/nwp_forcing/nc_ar'

# where to put the nc CHM file
settings['nc_chm_dir'] = '/Users/chris/Documents/science/code/SnowCast/v2/nwp_forcing/'

# where the CHM output is
settings['chm_outpath'] = '/Users/chris/Documents/science/code/SnowCast/v2/run_chm/output/meshes/SC.pvd'

#static figure output path
settings['fig_dir'] = '/Users/chris/Documents/science/code/SnowCast/v2/plot/figures'

# where to put the leaflet output
settings['html_dir'] = '/Users/chris/Documents/science/code/SnowCast/v2/www'

settings['domain'] = 'west'

# Define HRDPS variables to download (names match file names in HRDPS system)
settings['hrdps_variables'] = [ # temperature at various mb (Kevlin)
            'TMP_ISBL_1015', 'TMP_ISBL_1000', 'TMP_ISBL_0985', 'TMP_ISBL_0970', 'TMP_ISBL_0950', 'TMP_ISBL_0925',
            'TMP_ISBL_0900',

            # Geopotential Height of various mb (geopotential meter)
            'HGT_ISBL_1015', 'HGT_ISBL_1000', 'HGT_ISBL_0985', 'HGT_ISBL_0970', 'HGT_ISBL_0950',
            'HGT_ISBL_0925', 'HGT_ISBL_0900',

            # geopotential of Model surface (geopotential meter)
            'HGT_SFC_0',

            'TMP_TGL_2',  # 2m air temp (kelvin)
            'RH_TGL_2',   # 2m RH

            # Wind speed, direction 10m (m/s)
            'WIND_TGL_10', 'WDIR_TGL_10',

            # Surface pressure  (Pa)
            'PRES_SFC_0',

            # Incoming surface longwave, accumulated flux (J/m^2)
            'DLWRF_SFC_0',

            #Downward incident solar flux (Accumulated), surface, (J/m^2(
            'DSWRF_SFC_0',

            #precipitation rate, surface (kg/m^2/s)
            'PRATE_SFC_0',

            #accumulated precipitation, surface (kg/m^2)
            'APCP_SFC_0'
            ]


settings['hrdps2chm_names'] = {
                'orog': 'HGT_P0_L1_GST',
                't2m': 't',
                'r2': 'rh',
                'si10':'u',
                'wdir10':'vw_dir',
                'sp':'press',
                'ssrd': 'Qsi',
                'strd': 'Qli',
                'prate': 'p'
}

# force a regeneration of the complete nc archieve
settings['force_nc_archive'] = False

settings['dxdy'] = 150
settings['plot_vars'] = ['swe', 'snowdepthavg']
settings['dpi'] = 90

# Offset from UTM to local time (i.e. Mountain standard time = -7)
# CHM forcing files will be in this time zone
local_time_offset = 0

#### [min,max] extents for bounding box of latitude and longitude

# Bow river basin
# lat_r = [50.411581,51.218712]
# lon_r = [-115.793152,-114.362183]

# CRHO (crho_extent.tif)
lat_r = [50.66, 51.7933333333333]
lon_r = [-116.645, -114.769166666667]

# Entire GEM west domain
# lat_r = [0,90]
# lon_r = [-180,180]
