import glob
import os
import pandas as pd
import re
import urllib3
from datetime import datetime
from tqdm import tqdm
import time
from urllib3.exceptions import ProtocolError


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


def data_download(url, outputDir, filename, dryRun=False):
    ''' Function to download data from url, called by threading'''

    outputFile = os.path.join(outputDir,filename)

    if os.path.isfile(outputFile):
        print('File %s already exists. Download cancelled' % filename)
    elif not dryRun:
        retries = 11

        while True:
            http = urllib3.PoolManager(timeout=60, retries=5, num_pools=1)
            response = http.request('GET', url, preload_content=False)

            # if response.status != 200:
            #     return False

            retries -= 1
            try:
                with open(outputFile, 'wb') as out:
                    while True:
                        data = response.read(1024)
                        if not data:
                            break #end of file
                        out.write(data)
                response.release_conn()
                break
            except ProtocolError as e:
                print(f'Failed to download {url}, retries left = {retries}')
                if retries == 0:
                    raise e
                else:
                    time.sleep(60)

    return True


def backfill_grib2(settings):
    ''' Returns True if no backfill needed'''

    nc_files = {}
    date = []
    fname=[]

    # first, build a list
    all_files = glob.glob(os.path.join(settings['nc_ar_dir'], '*.nc'))

    try:
        config_start = pd.to_datetime(settings['start_date'], format='%Y-%m-%d')
    except KeyError as e:
        config_start = None

    for f in all_files:
        # assumption that we have 1 nc per day, and each nc has T+Xhr of forecast in it
        p = re.compile('([0-9]{4}-[0-9]{2}-[0-9]{2})')
        m = p.search(f)

        d = pd.to_datetime(m.group(1), format='%Y-%m-%d')

        # don't both looking for grib files if we have a partial archive that pre-dates our config start time
        if config_start is not None and d >= config_start:
            date.append(d)
            fname.append(f)
        elif config_start is None: # we don't have user start, so just add it
            date.append(d)
            fname.append(f)

    df = pd.DataFrame({'date':date, 'file':fname})
    df = df.sort_values(by=['date'])
    df = df.reset_index()

    start = None
    if len(df) == 0:
        print('No existing data found, using earliest available data on hpfx')
        start = find_hpfx_earliest_date()

        user_date = pd.to_datetime(settings['start_date'], format='%Y-%m-%d')
        if user_date  > start: #userdate comes /after/ hpfx start
            print('Earliest date on hpfx is older than configuration start date, using configuration start date: ' + settings['start_date'])
            start = user_date 

        start = start.strftime('%Y-%m-%d')

    else:
        start = df.date[0].strftime('%Y-%m-%d')

    end  = datetime.today().strftime('%Y-%m-%d') #df.date[len(df.date)-1].strftime('%Y-%m-%d %H:%M') # :-1 somehow returns the wrong item

    diff = pd.date_range(start = start,
                         end = end,
                         freq='1d').difference(df.date)


    if len(diff) == 0:
        print('No missing nc files')
        return True

    missing = '\n'.join([str(d) for d in diff.to_list()])
    # print(f'Missing the following dates: \n{missing}')

    leadTime = []
    for l in range(0, 48, 1):
        leadTime.append('%03d' % l)

    grib_to_download = []

    missing_files_error = False
    for missing in diff.to_list():
        print(f'Missing grib2 for {missing} ... ', end = '')

        Ymd = missing.strftime('%Y%m%d')

        #prefer backfilling of hpfx but also check dd if hpfx doesn't have today's as this occasioanlly occurs
        base_url_hpfx = f"""http://hpfx.collab.science.gc.ca/{Ymd}/WXO-DD/model_hrdps/{settings['hrdps_domain']}/2.5km/00/"""
        base_url_dd = f"""http://dd.weather.gc.ca/model_hrdps/{settings['hrdps_domain']}/2.5km/00/"""

        is_ok=True

        for var in settings['hrdps_variables']:

            for lead_time in leadTime:

                # these variables are not present at the 0h lead time as they are a rate or an accumulation
                if var in ['HGT_Sfc', 'PRATE_Sfc', 'APCP_Sfc'] and int(lead_time) == 0:
                    continue

                filename = f"""{Ymd}T00Z_MSC_HRDPS_{var}_RLatLon0.0225_PT{lead_time}H.grib2"""

                url_hpfx = f'{base_url_hpfx}/{lead_time}/{filename}'
                url_dd   = f'{base_url_dd}/{lead_time}/{filename}'

                url_for_download = url_hpfx

                if not os.path.exists(os.path.join(settings['grib_dir'], filename)):
                    ret = data_download(url_hpfx, settings['grib_dir'], filename, True)

                    if not ret:
                        ret = data_download(url_dd, settings['grib_dir'], filename, True)
                        if ret:
                            url_for_download = url_dd

                    if not ret:
                        print(f'\n\t[{var}@P{lead_time}] missing on hpfx, dd, and local archive [error]')
                        missing_files_error = True  # prepare to bail
                        is_ok = False

                # this let's us run the backfill before we do grib->nc, without accidentally downloading files we already have
                if not os.path.exists( os.path.join(settings['grib_dir'], filename)):
                    # can only backfill off the right URL
                    grib_to_download.append( ( url_for_download, filename) )

        if is_ok:
            print(f""" available on hpfx, dd, or local archive ({settings['grib_dir']})""")

    if missing_files_error:
        raise Exception('Missing grib files and not available on hpfx or local cache')

    download_failed = False
    for grib in tqdm(grib_to_download):
        ret = data_download(grib[0], settings['grib_dir'], grib[1])
        if not ret:
            print(f'Unable to obtain date {grib[1]}')
            download_failed = True

    # last ditched sanity check
    if download_failed:
        raise Exception('Missing grib files and not available on hpfx, dd, or local cache')

    return False  # we had to backfill
