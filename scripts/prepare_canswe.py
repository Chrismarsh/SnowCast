"""Checkout convenience wrapper; reusable processing lives in snowcast_runner."""
from pathlib import Path
import sys

from snowcast_runner.canswe import main


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    main(['--output', str(root / 'webui/public/observations/canswe'),
          '--bundle', str(root / 'webui/data/canswe-v8.zip'), *sys.argv[1:]])
