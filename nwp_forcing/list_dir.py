import pandas as pd
import glob
import os

def list_dir(dir, settings):
    all_files = glob.glob(os.path.join(dir, '*.nc'))
    date = []
    fname = []
    for f in all_files:
        p = re.compile('([0-9]{4}-[0-9]{2}-[0-9]{2})')
        m = p.search(f)

        d = pd.to_datetime(m.group(1), format='%Y-%m-%d')
        date.append(d)
        fname.append(f)

    df = pd.DataFrame({'date': date, 'file': fname})
    df = df.sort_values(by=['date'])
    df = df.reset_index()

    if len(df) == 0:
        raise Exception(f"There are no nc files in {settings['nc_ar_dir']}, ensure you have run grib2nc.")

    start = df.date[0].strftime('%Y-%m-%d')

    try:
        if settings['start_date'] is not None:
            start = pd.to_datetime(settings['start_date'], format='%Y-%m-%d')
            df = df[ df.date >= start]

            if len(df) == 0:
                raise Exception(f"No files were selected based on your start date of {start}. Ensure it is correct.")
    except KeyError as e:
        pass

    end = df.date.iloc[-1].strftime('%Y-%m-%d')

    try:
        if settings['end_date'] is not None:
            end = pd.to_datetime(settings['end_date'], format='%Y-%m-%d')
            df = df[df.date <= end]

            if len(df) == 0:
                raise Exception(f"No files were selected based on your end date of {end}. Ensure it is correct.")
    except KeyError as e:
        pass

    return df, start, end