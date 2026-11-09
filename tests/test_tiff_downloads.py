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
    ascii_name = 'swe_20260317230000.asc'
    result = indexer.make_index(row(fine) + row(indexer.SOURCE + coarse, '1.0G') + row(fine),
                                row(indexer.ASCII_SOURCE + ascii_name, '1.2M'))
    assert result['source'] == indexer.SOURCE
    assert result['ascii_source'] == indexer.ASCII_SOURCE
    assert result['files'] == [{'name': fine, 'size': '379M'}, {'name': ascii_name, 'size': '1.2M'}]


def test_rejects_external_links_unrecognized_grids_and_impossible_dates():
    good = 't-0.001x0.001_20260228T230000.tiff'
    bad = ['../' + good, 'https://example.com/' + good, good + '?download=1',
           good.replace('0228', '0230'), good.replace('0.001x0.001', '0.001x0.01'), 'catalog.json']
    ascii_name = 't_20260228230000.asc'
    bad_ascii = ['../' + ascii_name, 'https://example.com/' + ascii_name, ascii_name + '?x=1',
                 ascii_name.replace('0228', '0230'), ascii_name.replace('.asc', '.prj'),
                 ascii_name.replace('t_', 'unknown_'), indexer.SOURCE + ascii_name]
    result = indexer.make_index(row(good, '-') + ''.join(row(name) for name in bad),
                                row(ascii_name) * 2 + ''.join(row(name) for name in bad_ascii))
    assert result['files'] == [{'name': good, 'size': None}, {'name': ascii_name, 'size': '379M'}]


def test_empty_or_failed_refresh_never_replaces_a_working_index(tmp_path, monkeypatch):
    output = tmp_path / 'index.json'
    original = indexer.make_index(row('swe-0.001x0.001_20260317T230000.tiff'), row('swe_20260317230000.asc'))
    indexer.write_index(original, output)
    html = tmp_path / 'listing.html'
    html.write_text('<h1>Service unavailable</h1>')
    ascii_html = tmp_path / 'ascii.html'
    ascii_html.write_text(row('swe_20260317230000.asc'))
    with pytest.raises(ValueError, match='no recognized TIFF'):
        indexer.refresh(output, html, ascii_listing=ascii_html)
    assert json.loads(output.read_text()) == original

    def failed(*args, **kwargs):
        raise TimeoutError('network timeout')
    monkeypatch.setattr(indexer, 'urlopen', failed)
    indexer.refresh(output, allow_stale=True)
    assert json.loads(output.read_text()) == original
    with pytest.raises(TimeoutError):
        indexer.refresh(tmp_path / 'absent.json', allow_stale=True)


def test_ascii_failure_retains_both_previous_archives(tmp_path, monkeypatch):
    original = indexer.make_index(row('swe-0.001x0.001_20260317T230000.tiff'), row('swe_20260317230000.asc'))
    output = tmp_path / 'index.json'
    indexer.write_index(original, output)
    html, ascii_html = tmp_path / 'tiff.html', tmp_path / 'ascii.html'
    html.write_text(row('swe-0.001x0.001_20260318T230000.tiff'))
    ascii_html.write_text('<h1>Service unavailable</h1>')
    with pytest.raises(ValueError, match='no recognized ASCII'):
        indexer.refresh(output, html, ascii_listing=ascii_html)
    assert json.loads(output.read_text()) == original
    # Verify the normal refresh reads both actual archive roots before replacing.
    sources = []
    def listing(source, path):
        sources.append(source)
        return row('swe_20260318230000.asc') if source == indexer.ASCII_SOURCE else html.read_text()
    monkeypatch.setattr(indexer, 'read_listing', listing)
    indexer.refresh(output)
    assert sources == [indexer.SOURCE, indexer.ASCII_SOURCE]
    assert [f['name'] for f in json.loads(output.read_text())['files']] == [
        'swe-0.001x0.001_20260318T230000.tiff', 'swe_20260318230000.asc']
