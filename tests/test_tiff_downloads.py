import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('download_index', Path(__file__).parents[1] / 'scripts/index_tiff_downloads.py')
indexer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(indexer)


def row(name, size='379M'):
    return f'<tr><td><img alt="[IMG]"></td><td><a href="{name}">shortened name</a></td><td>2026-03-18 10:45</td><td>{size}</td><td></td></tr>'


def test_parses_real_directory_layout_and_utc_filenames():
    fine = 'swe-0.001x0.001_20260317T230000.tiff'
    coarse = 'snowdepthavg-0.01x0.01_20260316T230000.tiff'
    result = indexer.make_index(row(fine) + row(indexer.SOURCE + coarse, '1.0G') + row(fine))
    assert result['source'] == indexer.SOURCE
    assert result['files'] == [{'name': coarse, 'size': '1.0G'}, {'name': fine, 'size': '379M'}]


def test_rejects_external_links_unrecognized_grids_and_impossible_dates():
    good = 't-0.001x0.001_20260228T230000.tiff'
    bad = ['../' + good, 'https://example.com/' + good, good + '?download=1',
           good.replace('0228', '0230'), good.replace('0.001x0.001', '0.001x0.01'), 'catalog.json']
    result = indexer.make_index(row(good, '-') + ''.join(row(name) for name in bad))
    assert result['files'] == [{'name': good, 'size': None}]


def test_empty_or_failed_refresh_never_replaces_a_working_index(tmp_path, monkeypatch):
    output = tmp_path / 'index.json'
    original = indexer.make_index(row('swe-0.01x0.01_20260317T230000.tiff'))
    indexer.write_index(original, output)
    html = tmp_path / 'listing.html'
    html.write_text('<h1>Service unavailable</h1>')
    with pytest.raises(ValueError, match='no recognized TIFF'):
        indexer.refresh(output, html)
    assert json.loads(output.read_text()) == original

    def failed(*args, **kwargs):
        raise TimeoutError('network timeout')
    monkeypatch.setattr(indexer, 'urlopen', failed)
    indexer.refresh(output, allow_stale=True)
    assert json.loads(output.read_text()) == original
    with pytest.raises(TimeoutError):
        indexer.refresh(tmp_path / 'absent.json', allow_stale=True)
