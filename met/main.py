import glob
import natsort
import xarray as xr
from pathlib import Path
import json
import pandas as pd


# Update the metdata.json 
def update_metdata_json(settings):

    print("Creating met json")

    for met_ar in [ 'hrdps']:

        metadata_list = []
        # Read existing if required
        json_fname = f'met/metdata-{met_ar}.json'
        if Path(json_fname).is_file():
            with open(json_fname, 'r') as f:
                metadata_list = json.load(f)

        file_paths = natsort.natsorted(glob.glob(f'met/{met_ar}/*.nc'))

        most_recent = None
        if metadata_list:
            most_recent = pd.to_datetime(metadata_list[-1]['start_time'])


        for file_path in file_paths:
            if most_recent is not None:
                this_file_date = pd.to_datetime(Path(file_path).stem, format="%Y%m%d")
                if this_file_date <= most_recent:
                    continue

            print(file_path)
            ds = xr.open_mfdataset(file_path)

            metadata = {
                "start_time": str(ds.time.min().dt.strftime("%Y%m%dT%H%M%S").values),  # Convert to string for JSON serialization
                "end_time": str(ds.time.max().dt.strftime("%Y%m%dT%H%M%S").values),
                "file_name": str(Path(file_path).resolve())
            }

            metadata_list.append(metadata)

            ds.close()

        # print(metadata_list)
        with open(json_fname, 'w') as f:
            json.dump(metadata_list, f, indent=4)
