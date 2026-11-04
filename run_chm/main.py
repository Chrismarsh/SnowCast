import subprocess
import os
import shutil
import pandas as pd
import sys
from pathlib import Path

import json # to pretty print the output
import json5 as pyjson5# to be able to handle comments in json loading


def prune_checkpoints(settings, keep_days=3):
    """Delete old daily checkpoints, keeping the newest `keep_days`.

    Each checkpoint is a pair in run_chm/output/checkpoint/:
        checkpoint_<ts>.np800.json      (index file listing the per-rank data)
        <ts>/chkp<ts>_<rank>.nc         (per-rank state, ~14 GB total)
    The filename timestamp is fixed-width so lexicographic order ==
    chronological order. CHM auto-resumes from the newest checkpoint, so
    anything older than that (with a little headroom for rollback) is safe
    to delete. Never raises: a partial prune failure must not take the
    pipeline down.
    """
    chk_dir = Path(settings['chm_outpath']).resolve().parent / 'checkpoint'
    if not chk_dir.is_dir():
        print(f'No checkpoint directory at {chk_dir}; nothing to prune')
        return

    jsons = sorted(chk_dir.glob('checkpoint_*.json'))
    for j in jsons[:-keep_days]:
        ts = j.stem.rsplit('.', 1)[0].removeprefix('checkpoint_')  # checkpoint_<ts>.np800.json -> <ts>
        try:
            shutil.rmtree(chk_dir / ts, ignore_errors=True)
            j.unlink(missing_ok=True)
            print(f'Pruned checkpoint {ts}')
        except OSError as e:
            print(f'Could not prune checkpoint {ts}: {e}')


def main(settings):

    with open(settings['chm_config_path']) as f:
        config = pyjson5.load(f)

    config['output']['ugrid']['variables'] = settings['plot_vars']

    # once we get going from a checkpoint, this will be ignored by the checkpoint loader in CHM
    config['option']['startdate'] = pd.to_datetime(settings['start_date']).isoformat().replace(":",'').replace("-",'')

    with open(settings['chm_config_path'], 'w') as f:
        js = json.dumps(config, indent=2)
        f.write(js)

    print("Running CHM")

    # clean up the clean_exit flag other wise the CHM job will bail
    path = "run_chm/output/clean_exit"
    if os.path.exists(path):
        os.remove(path)
        print(f"Removed {path}")

    exec_str = settings['chm_exec_str']

    result = subprocess.run(
        exec_str,
        check=False,
        capture_output=True,
        shell=True,
        text=True,
        cwd=os.path.join(settings['snowcast_base'], 'run_chm'),
    )

    print(result.stdout)

    if result.returncode == 0:
        pass  # normal success, never used
    elif result.returncode == 20:
        # exited out via clean_exit. Assuming success
        pass
    elif result.returncode == 30:
        # we don't have enough met to resume. Not a failure per-se but nothing to be done
        print(f"Not enough met data to resume from checkpoint. Continuing with post processing EXISTING output.")

    else:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"CHM failed with exit {result.returncode}")

    print("Finished")

    # house keeping: keep only the newest N daily checkpoints (older ones are
    # never needed again since CHM auto-resumes from the newest checkpoint)
    prune_checkpoints(settings, keep_days=settings.get('checkpoint_keep_days', 3))




