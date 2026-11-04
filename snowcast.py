# import dask
import importlib
import os
import socket
import sys
import threading

from datetime import datetime
import pickle
from notifier import slack
from met import main as met_main
from plot import main as plot_main
from run_chm import main as chm_main
from webupload import upload
from postprocess import postprocess
from pathlib import Path

import dask
dask.config.set(**{'array.slicing.split_large_chunks': False})
dask.config.set(scheduler='single-threaded')

# ---------------------------------------------------------------------------
# Lock management
#
# The lock is a small text file so a new run can inspect the previous owner
# (pid, host, heartbeat) and only removes it when there is POSITIVE evidence
# the owner is no longer running. A running job - of any duration, including
# multi-day backfills - therefore never gets its lock stolen.
#
#   same host   -> os.kill(pid, 0): alive = keep (any age), dead = stale
#   else        -> trust last_heartbeat: missing/stale after STALE_AFTER = stale
#
# A daemon thread refreshes last_heartbeat while a run is in progress, so
# long runs stay fresh. A killed/crashed process stops heartbeating and the
# lock goes stale automatically.
# ---------------------------------------------------------------------------

LOCK_FILE = '.snowcast.lock'
HEARTBEAT_INTERVAL = 60   # seconds between heartbeat writes
STALE_AFTER = 15 * 60     # seconds without liveness evidence before a
                          # cross-host/legacy lock is considered stale


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True        # exists, owned by someone else
    return True


def _write_lock_file(path):
    with open(path, 'w') as f:
        f.write(
            f"pid={os.getpid()} host={socket.gethostname()} "
            f"started={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')} "
            f"last_heartbeat={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n"
        )
        f.flush()
        os.fsync(f.fileno())


def _refresh_heartbeat(path):
    try:
        with open(path) as f:
            info = dict(p.split('=', 1) for p in f.read().split())
        info['last_heartbeat'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        _write_lock_file(path)  # rewrite whole file (small) - keeps it atomic-ish
    except OSError as e:
        print(f"Warning: failed to refresh lock heartbeat: {e}")


def is_stale(path, info):
    """Return True when there is positive evidence the lock owner is gone."""
    host = info.get('host')
    pid = int(info['pid']) if info.get('pid', '').lstrip('-').isdigit() else 0

    if host == socket.gethostname() and pid > 0:
        return not _pid_alive(pid)      # live on this host -> NEVER stale, any age

    # Cross-host, or legacy 0-byte lock: trust the heartbeat (mtime fallback)
    try:
        ref = datetime.strptime(info.get('last_heartbeat', ''), '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        ref = datetime.fromtimestamp(os.path.getmtime(path))
    return (datetime.now() - ref).total_seconds() > STALE_AFTER


def acquire_lock():
    """Create the lock, removing a stale one first. Exit 0 if live run found."""
    if not os.path.exists(LOCK_FILE):
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)
        except FileExistsError:
            pass                        # lost a race; re-check below
        else:
            with os.fdopen(fd, 'w') as f:
                f.write(
                    f"pid={os.getpid()} host={socket.gethostname()} "
                    f"started={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')} "
                    f"last_heartbeat={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n"
                )
                f.flush()
                os.fsync(f.fileno())
            return

    info = {}
    try:
        with open(LOCK_FILE) as f:
            info = dict(p.split('=', 1) for p in f.read().split())
    except OSError:
        pass                            # treat as legacy/empty

    if is_stale(LOCK_FILE, info):
        owner = f"pid={info.get('pid', '?')} host={info.get('host', '?')}"
        print(f"Removing stale lock (previous owner {owner}).")
        try:
            os.remove(LOCK_FILE)
        except OSError as e:
            print(f"Warning: could not remove stale lock: {e}")
            print('Snowcast is already running')
            sys.exit(0)
        return acquire_lock()

    print('Snowcast is already running')
    sys.exit(0)


def heartbeat_worker(path):
    while True:
        _refresh_heartbeat(path)
        threading.Event().wait(HEARTBEAT_INTERVAL)


import argparse
parser = argparse.ArgumentParser()
parser.add_argument("-m", "--no-met", required=False, dest='met', action="store_false", help="Update met archive json")
parser.add_argument("-r", "--no-chm", required=False, dest='CHM', action="store_false", help="Run CHM")
parser.add_argument("-p", "--no-plot", required=False, dest='plot', action="store_false", help="Do plot")
parser.add_argument("-a", "--no-postprocess", required=False, dest='postprocess', action="store_false", help="Post process CHM->TIFF")
parser.add_argument("-u", "--no-upload", required=False, dest='upload', action="store_false", help="Upload")
parser.add_argument("-c", "--config", required=True, default='', type=str,
                help="Config file to use")

if __name__ == '__main__':

    args = vars(parser.parse_args())

    acquire_lock()

    step_met = args['met']
    step_CHM = args['CHM']
    step_plot = args['plot']
    step_upload = args['upload']
    step_postprocess = args['postprocess']

    print("Started at =", datetime.now().strftime("%H:%M:%S"))

    # Get name of configuration file/module
    configfile = args['config']

    # Load in configuration file as module
    X = importlib.machinery.SourceFileLoader('config', configfile)
    X = X.load_module()

    # Assing to local variables
    settings = X.settings

    # keep the lock fresh while the (possibly multi-hour) run is in progress
    hb_thread = threading.Thread(target=heartbeat_worker, args=(LOCK_FILE,), daemon=True)
    hb_thread.start()


    #######################################################

    # slack.send_slack_notifier(settings['webhook_url'], 'Snowcast run started :zap:', '')


    try:
        try:
            if step_met:
                met_main.update_metdata_json(settings)
        except Exception as e:
            message = 'Snowcast run failed during CHM run :exclamation:\n' + str(e)
            slack.send_slack_notifier(settings['webhook_url'], message, '')
            raise Exception(message)

        try:
            if step_CHM:
                chm_main.main(settings)
        except Exception as e:
            message = 'Snowcast run failed during CHM run :exclamation:\n' + str(e)
            slack.send_slack_notifier(settings['webhook_url'], message, '')
            raise Exception(message)

        try:
            if step_postprocess:
                postprocess.main(settings)

        except Exception as e:
            message = 'Snowcast run failed during post processing :exclamation:\n' + str(e)
            slack.send_slack_notifier(settings['webhook_url'], message, '')

            raise Exception(message)

        try:
            if step_plot:
                plot_main.main(settings)
        except Exception as e:
            message = 'Snowcast run failed during plot generation :exclamation:\n' + str(e)
            slack.send_slack_notifier(settings['webhook_url'], message, '')
            raise Exception(message)

        try:
            if step_upload:
                upload.upload(settings)
        except Exception as e:
            message = 'Snowcast run failed during web upload :exclamation:\n' + str(e)
            slack.send_slack_notifier(settings['webhook_url'], message, '')
            raise Exception(message)
    finally:
        hb_thread.join(timeout=1)
        message = "Finished at " + datetime.now().strftime("%H:%M:%S")
        # slack.send_slack_notifier(settings['webhook_url'], message, '')

        print(message)

        os.remove('.snowcast.lock')
        