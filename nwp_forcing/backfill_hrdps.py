import glob
import os
import pandas as pd
import re
import urllib3
from datetime import datetime
from tqdm import tqdm


def find_hpfx_earliest_date():
    http = urllib3.PoolManager()
    r = http.request('GET', 'http://hpfx.collab.science.gc.ca/')
    data = str(r.data)

    r = re.compile("a href=\"([0-9]{8})/\"")
    m = r.search(str(data))


    try:
        date = m.group(1)
        date = pd.to_datetime(date, format='%Y%m%d')
    except:
        raise Exception('Could not determine start time of hpfx archive')

    return date


def data_download(url, outputDir, filename):
    ''' Function to download data from url, called by threading'''
    
    useThreading = False
    
    outputFile = os.path.join(outputDir,filename)

    if os.path.isfile(outputFile):
        print('File %s already exists. Download cancelled' % filename)
    else:
            http = urllib3.PoolManager(timeout=60, retries=5, num_pools = 1)
            response = http.request('GET',url,preload_content=False)

            if response.status != 200:
                return False

            with open(outputFile, 'wb') as out:
                while True:
                    data = response.read(1024)
                    if not data:
                        break
                    out.write(data)

            response.release_conn()
            # url = url.replace('&','&amp;')
            # print('Downloading url complete [%s]' %url)

    return True


def backfill_grib2(settings):
    ''' Returns True if no backfill needed'''

    nc_files = {}
    date = []
    fname=[]

    # first, build a list
    all_files = glob.glob(os.path.join(settings['nc_ar_dir'],'*.nc'))

    for f in all_files:
        p = re.compile('([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})')
        m = p.search(f)

        d = pd.to_datetime(m.group(1), format='%Y-%m-%dT%H:%M:%S')
        date.append(d)
        fname.append(f)

    df = pd.DataFrame({'date':date, 'file':fname})
    df = df.sort_values(by=['date'])
    df = df.reset_index()

    start = None
    if len(df) == 0:
        print('No existing data found, using earliest available data on hpfx')
        start = find_hpfx_earliest_date().strftime('%Y-%m-%d 00:00')
    else:
        start = df.date[0].strftime('%Y-%m-%d %H:%M')

    end  = datetime.today().strftime('%Y-%m-%d 00:00') #df.date[len(df.date)-1].strftime('%Y-%m-%d %H:%M') # :-1 somehow returns the wrong item
    diff = pd.date_range(start = start,
                         end = end,
                         freq='1d').difference(df.date)


    if len(diff) == 0:
        print('No missing nc files')
        return True

    missing = '\n'.join([str(d) for d in diff.to_list()])
    print(f'Missing the following dates: \n{missing}')

    leadTime = []
    for l in range(0, 48, 1):
        leadTime.append('%03d' % l)

    grib_to_download = []

    for missing in diff.to_list():
        print(f'Checking for date={missing} on hpfx archive...')

        Ymd = missing.strftime('%Y%m%d')

        base_url = f'http://hpfx.collab.science.gc.ca/{Ymd}/WXO-DD/model_hrdps/west/grib2/00/'

        for var in settings['hrdps_variables']:
            for lead_time in leadTime:
                filename = f'CMC_hrdps_west_{var}_ps2.5km_{Ymd}00_P{lead_time}-00.grib2'

                # this let's us run the backfill before we do grib->nc, without accidentally downloading files we already have
                if not os.path.exists( os.path.join(settings['grib_dir'],filename)):
                    url = f'{base_url}/{lead_time}/{filename}'
                    grib_to_download.append( (url,filename) )


    for grib in tqdm(grib_to_download):
        ret = data_download(grib[0], settings['grib_dir'], grib[1])
        if not ret:
            print(f'Unable to obtain date {grib[1]}')

    return False # we had to backfill