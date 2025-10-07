import glob
import natsort
import xarray as xr
from pathlib import Path
import json


# Update the metdata.json 
def update_metdata_json(settings):

    print("Creating met json")

    for met_ar in [ 'hrdps']: 

        file_paths = natsort.natsorted(glob.glob(f'{met_ar}/*.nc'))
        metadata_list = []
        for file_path in file_paths:
            print(file_path)
            ds = xr.open_mfdataset(file_path)

            metadata = {
                "start_time": str(ds.time.min().dt.strftime("%Y%m%dT%H%M%S").values),  # Convert to string for JSON serialization
                "end_time": str(ds.time.max().dt.strftime("%Y%m%dT%H%M%S").values),
                "file_name": str(Path(file_path).resolve())
            }

            metadata_list.append(metadata)

            ds.close()

        print(metadata_list)
        with open(f'metdata-{met_ar}.json', 'w') as f:
            json.dump(metadata_list, f, indent=4)
