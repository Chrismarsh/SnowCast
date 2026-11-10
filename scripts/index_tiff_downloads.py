"""Compatibility entry point; implementation lives in the installed SnowCast package."""
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from snowcast_runner import downloads as _implementation

if __name__ == '__main__':
    if not any(arg == '--output' or arg.startswith('--output=') for arg in sys.argv[1:]):
        sys.argv.extend(['--output', str(Path(__file__).resolve().parents[1] / 'webui/public/download-index.json')])
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
