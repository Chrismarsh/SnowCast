"""Compatibility entry point; implementation lives in the installed SnowCast package."""
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from snowcast_runner import met as _implementation

from snowcast_runner.met import read_index, update_index


def update_metdata_json(settings):
    """Legacy snowcast.py adapter using the same incremental indexer."""
    result = update_index('met/hrdps', 'met/metdata-hrdps.json', start_date=settings.get('start_date'))
    print(f'Met metadata: added {result["added"]} files; {result["files"]} total')
    return result
