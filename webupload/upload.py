import subprocess
import shutil
import glob
import os
import time
from contextlib import contextmanager

@contextmanager
def set_cwd(path):
    prev_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)


from collections import defaultdict


def _rolling_copy(filemask, path, archive_dir, ntokeep=3):
    files = sorted(glob.glob(filemask))

    os.makedirs(path, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)

    # Group by variable name (everything before the timestamp)
    groups = defaultdict(list)

    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]

        # snowdepthhavg-0.001x0.001_20260531T230000
        var = stem.rsplit("_", 1)[0]

        groups[var].append(f)

    for var, var_files in groups.items():
        var_files.sort()

        keep = set(var_files[-ntokeep:])

        for f in var_files:
            if f not in keep:
                print(f"Archiving {f}")
                shutil.move(
                    f,
                    os.path.join(archive_dir, os.path.basename(f))
                )

        for f in sorted(keep):
            dest = os.path.join(path, os.path.basename(f))
            # The kept files may already sit at their destination. With the
            # current layout the TIFFs live in postprocess/tiff/ and that is
            # also the webupload target dir (path), so copying in place would
            # raise shutil.SameFileError. Treat an already-placed file as done.
            if os.path.exists(dest) and os.path.samefile(f, dest):
                print(f"Keeping {f} in place (already at {dest})")
                continue
            print(f"Copying {f} for webupload")
            shutil.copy2(f, path)

def upload(settings):

    tiff_path = os.path.join(settings['html_dir'], 'tif')
    asc_path = os.path.join(settings['html_dir'], 'asc')
    #
    # _cleanup_dir(tiff_path)
    # _cleanup_dir(asc_path)
    #
    # for file_type in ['swe_*.asc', 'swe_*.prj']:
    #     _rolling_copy(file_type, asc_path)
    #
    # for file_type in ['swe-0.001x0.002*.tiff', 'swe-0.036x0.036*.tiff']:
    #     _rolling_copy(file_type, tiff_path, 3)

    #
    print('rsyncing outputs...')
    with set_cwd("postprocess/"):
        print(os.getcwd())

        # TIFFs are written into the postprocess/tiff/ subdir (chm_ugrid2grid
        # runs with --tiff-output ./tiff); .asc/.prj still land at the top
        # level. Map each ext to the subdir that holds it.
        ext_subdir = {"asc": "", "tiff": "tiff", "prj": ""}

        for ext in ["asc", "tiff", "prj"]:
            subdir = ext_subdir[ext]
            files = glob.glob(os.path.join(subdir, f"*.{ext}")) if subdir else glob.glob(f"*.{ext}")
            if ext == "tiff" and not files:
                # An empty tiff glob used to silently skip the upload and leave
                # the public downloads stale for months with no sign. Make it
                # loud and greppable so a missing/regressed TIFF path is caught
                # the same day. We warn (rather than raise) because:
                #   * postprocess/tiff/ is legitimately empty during the
                #     submit_ugrid2tiff.sh run -- it sweeps tiff/ into
                #     archive_tiff/ at job start and only refills it after the
                #     full 800-rank chm_ugrid2grid run completes, so the upload
                #     cron can race that window; and
                #   * a raise here would abort the rest of upload(), including
                #     the webui/v3 COG upload, which is independent and working.
                print("WARNING: postprocess/tiff/ contains no .tiff files -- "
                      "TIFF upload SKIPPED. Public original-TIFF downloads will "
                      "stay stale until new TIFFs are produced. Did the TIFF "
                      "postprocess job (submit_ugrid2tiff.sh / sc_2tiff) finish?")
            for f in files:
                print(f)
                src = os.path.join(os.getcwd(), f)  # your local file
                dst = f"collab-lp:/home/chm003/project/snowcast/{ext}/"

                cmd = f"rsync --progress {src} {dst}"

                result = subprocess.run(cmd, stdin=subprocess.DEVNULL, text=True, capture_output=True, shell=True)

                print(result.stdout)
                # print(result.stderr)
                if result.returncode != 0:
                    print("STDERR:", result.stderr)
                    print("Exit code:", result.returncode)
                    raise Exception(f"rsync failed with exit code {result.returncode}")

    print('Uploading to webhost...')

    retry = 0
    done = False
    current_delay = 30 # sec

    while retry < 10 and not done:
        try:
            # -I to ensure that the quick size/time check is skipped and we always upload the tiles
            # --delete to update remote if we remove files locally
            exec_str = 'rsync -rIt --progress --inplace --force --delete --perms --chmod=0755 %s/ root@www.snowcast.ca:/var/www/html/v2/' % settings['html_dir']
            subprocess.check_call([exec_str], shell=True)
            done = True
        except:
            print("Upload to snowcast failed")
            retry = retry + 1
            time.sleep(current_delay)
            current_delay *= 2

    if not done:
        raise Exception("Failed to upload to Snowcast")

    # _rolling_copy() globs relative to the cwd, but this call used to run from
    # the repo root (after the set_cwd("postprocess/") block above) where no
    # *.tiff exists, so it silently archived nothing. TIFFs now live in
    # postprocess/tiff/; run the glob there. The path/archive_dir targets below
    # are absolute, so they are unaffected by the cwd.
    with set_cwd("postprocess/tiff/"):
        _rolling_copy(
            "*.tiff",
            path="/home/chm003/project/Snowcast-www/SnowCast/postprocess/tiff/",
            archive_dir="/home/chm003/project/Snowcast-www/SnowCast/postprocess/archive_tiff/",
            ntokeep=3,
        )

    print('done')

    if settings.get('webui_enabled', False) and settings.get('webui_upload_host'):
        from . import v3
        if not settings.get('webui_upload_dir'):
            raise ValueError('webui_upload_dir is required with webui_upload_host')
        v3.upload(settings['webui_data_dir'], settings['webui_upload_host'], settings['webui_upload_dir'],
                  settings.get('webui_download_index_dir'))
