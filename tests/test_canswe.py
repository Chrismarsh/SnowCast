import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import numpy as np
import pytest

from snowcast_runner import canswe
from snowcast_runner.cli import main
from snowcast_runner.site_config import load_site


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / 'scripts' / f'{name}.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


unpacker = module('unpack_canswe')


def row(date, swe, depth=None, agency='', qc=''):
    return [date, swe, depth, agency, '', qc, '']


def test_seasonal_statistics_give_each_year_one_vote_and_preserve_zero():
    rows = [row(f'{year}-04-01', value) for year, value in zip(range(2000, 2010), range(0, 100, 10))]
    # Many daily samples in a single year cannot dominate the historic range.
    rows += [row(f'2009-04-{day:02d}', 90) for day in range(2, 16)]
    result = canswe.summaries(rows, 1)[16]
    assert result['years'] == 10
    assert result['median'] == 45
    assert result['q25'] == 22.5 and result['q75'] == 67.5
    assert result['first'] == 2000 and result['last'] == 2009
    assert result['samples'] == []


def test_sparse_bins_remain_discrete_and_depth_missing_is_not_zero():
    rows = [row('2020-04-01', 0), row('2021-04-02', 60), row('2021-05-25', 120)]
    result = canswe.summaries(rows, 1)
    assert result[16]['median'] is None
    assert result[16]['samples'] == [[2020, 0.0], [2021, 60.0]]
    assert result[17]['years'] == 0 and result[17]['samples'] == []
    assert all(b['years'] == 0 for b in canswe.summaries(rows, 2))


def test_qc_and_agency_exclusions_are_variable_specific():
    rows = [row('2020-04-01', 20, 0.2, agency=flag) for flag in ['A', 'C', 'E', 'G', 'M', 'Y']]
    rows += [row('2020-04-02', 30, qc='W'), row('2020-04-03', None)]
    assert canswe.summaries(rows, 1)[16]['years'] == 0
    assert canswe.summaries(rows, 2)[16]['samples'] == [[2020, 0.2]]
    for flag in ['', 'B', 'P', 'R', 'T']:
        assert canswe.summaries([row('2020-04-01', 0, agency=flag)], 1)[16]['samples'] == [[2020, 0]]


def test_snow_season_and_finite_missing_values():
    from datetime import date
    assert canswe.snowyear(date(2024, 8, 1)) == 2025
    assert canswe.snowyear(date(2025, 7, 31)) == 2025
    assert canswe.halfmonth(date(2024, 2, 29)) == 13
    assert canswe.number(np.ma.masked) is None
    assert canswe.number(float('nan')) is None
    assert canswe.number(0) == 0


def test_bundled_snapshot_and_representative_scientific_edge_cases(tmp_path):
    root = Path(__file__).parents[1]
    bundle = root / 'webui/data/canswe-v8.zip'
    unpacker.unpack(bundle, tmp_path)
    index = json.loads((tmp_path / 'index.json').read_text())
    assert index['stations']
    assert len({s['id'] for s in index['stations']}) == len(index['stations'])
    assert index['dataset']['source_md5'] == canswe.SOURCE_MD5
    boxes = [d['bounds'] for d in index['domains']] if 'domains' in index else [index['bounds']]
    for station in index['stations']:
        assert any(b[0] <= station['lon'] <= b[2] and b[1] <= station['lat'] <= b[3] for b in boxes)
        detail = json.loads(gzip.decompress((tmp_path / station['href']).read_bytes()))
        assert detail['id'] == station['id']
        assert all(detail['records'][i][0] < detail['records'][i+1][0] for i in range(len(detail['records'])-1))
        assert all(b['median'] is None if b['years'] < 10 else b['median'] is not None for b in detail['seasonal']['swe'])
        if station['id'] == 'ALE-05BJ805P':
            assert station['counts']['swe'] > 10000 and station['counts']['depth'] == 0
            assert all(b['years'] == 0 for b in detail['seasonal']['depth'])
        if 'FORTRESS' in station['name'].upper():
            assert any(b['samples'] for b in detail['seasonal']['swe'])
            assert all(b['median'] is None for b in detail['seasonal']['swe'])


def test_unpack_rejects_paths_outside_static_snapshot(tmp_path):
    bundle = tmp_path / 'bad.zip'
    with zipfile.ZipFile(bundle, 'w') as archive:
        archive.writestr('index.json', json.dumps({'version': 1, 'stations': [{'href': '../../escape.json.gz'}]}))
    with pytest.raises(ValueError, match='path'):
        unpacker.unpack(bundle, tmp_path / 'public')
    assert not (tmp_path / 'escape.json.gz').exists()


@pytest.fixture
def regional_source(tmp_path, monkeypatch):
    """Tiny real NetCDF: two domains, overlap, boundaries and excluded stations."""
    from netCDF4 import Dataset
    source = tmp_path / 'observations.nc'
    points = [('west', -115, 51), ('tvc', -133.5, 68.75), ('gap', -125, 60),
              ('outside', -100, 45), ('edge', -134, 68), ('HQ-test', -72, 50)]
    with Dataset(source, 'w') as data:
        data.createDimension('station', len(points))
        data.createDimension('time', 2)
        data.createDimension('character', 1)
        time = data.createVariable('time', 'i4', ('time',))
        time.units, time.calendar = 'days since 2020-04-01', 'standard'
        time[:] = [0, 1]
        for key, values in {'station_id': [p[0] for p in points],
                            'station_name': [p[0].upper() for p in points],
                            'source': ['GNWT'] * len(points)}.items():
            data.createVariable(key, str, ('station',))[:] = np.array(values, dtype=object)
        for key, values in {'lon': [p[1] for p in points], 'lat': [p[2] for p in points],
                            'elevation': [100] * len(points), 'type_mes': [0] * len(points)}.items():
            data.createVariable(key, 'f8', ('station',))[:] = values
        for key, units, values in [('snw', 'kg m**-2', [0, 20]), ('snd', 'm', [.1, .2])]:
            variable = data.createVariable(key, 'f4', ('station', 'time'), fill_value=-9999)
            variable.units = units
            variable[:] = np.tile(values, (len(points), 1))
        for key in ['data_flag_snw', 'data_flag_snd', 'qc_flag_snw', 'qc_flag_snd']:
            data.createVariable(key, 'S1', ('station', 'time', 'character'))[:] = b''
    monkeypatch.setattr(canswe, 'SOURCE_MD5', hashlib.md5(source.read_bytes()).hexdigest())
    return source


@pytest.fixture
def regional_site(tmp_path):
    # Project grid bounds can be projected; the published catalogue is WGS84.
    projects = []
    for name, bounds in [('west', [-132, 46.4, -109.8, 56]), ('tvc', [-134, 68, -132, 70]),
                         ('overlap', [-117, 50, -113, 53])]:
        project = tmp_path / 'projects' / name
        project.mkdir(parents=True)
        (project / 'snowcast.json').write_text(json.dumps({'version': 2, 'id': name,
            'model': {'config': 'not-needed.json'}, 'forcing': {'archive': '/not-needed'},
            'postprocess': {'grid': {'crs': 'EPSG:3857', 'bounds': [-1e7, 1e6, -1e6, 1e7]}}}))
        projects.append(f'../projects/{name}')
        directory = tmp_path / 'staging/data' / name
        directory.mkdir(parents=True)
        (directory / 'catalog.json').write_text(json.dumps({'version': 1, 'domain': {'id': name}, 'bounds': bounds}))
    site_file = tmp_path / 'sites/site.json'
    site_file.parent.mkdir()
    site_file.write_text(json.dumps({'version': 1, 'projects': projects, 'staging': '../staging',
                                    'deploy': {'host': 'fixture.example', 'directory': '/var/www/html/v3-testing'}}))
    return site_file


def test_site_bundle_selects_union_deduplicates_and_follows_project_changes(regional_source, regional_site, tmp_path, monkeypatch, capsys):
    import subprocess
    monkeypatch.chdir(tmp_path.parent)  # Site paths are relative to the config, not cwd.
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Bundle generation must remain local'))
    bundle = tmp_path / 'ui/data/canswe.zip'
    command = ['site', 'prepare-canswe', str(regional_site), '--source', str(regional_source), '--bundle', str(bundle)]
    assert main(command) == 0
    assert 'tvc (tvc): 2 CanSWE stations' in capsys.readouterr().out
    with zipfile.ZipFile(bundle) as archive:
        index = json.loads(archive.read('index.json'))
        assert {s['id'] for s in index['stations']} == {'west', 'tvc', 'edge'}
        assert len(index['stations']) == 3  # Overlapping domains do not duplicate histories.
        assert [d['id'] for d in index['domains']] == ['west', 'tvc', 'overlap']
        assert index['bounds'] == [-134, 46.4, -109.8, 70]
        assert str(tmp_path) not in json.dumps(index) and 'fixture.example' not in json.dumps(index)
        for station in index['stations']:
            detail = json.loads(gzip.decompress(archive.read(station['href'])))
            assert detail['id'] == station['id'] and detail['records'][0][1] == 0
    before = bundle.read_bytes()
    assert main(command) == 0 and bundle.read_bytes() == before  # Reproducible.
    unpacker.unpack(bundle, tmp_path / 'public')  # Same format as npm's build hook.
    raw = json.loads(regional_site.read_text())
    raw['projects'] = raw['projects'][:1]
    regional_site.write_text(json.dumps(raw))
    assert main(command) == 0
    with zipfile.ZipFile(bundle) as archive:
        assert [s['id'] for s in json.loads(archive.read('index.json'))['stations']] == ['west']
    assert not any((tmp_path / 'projects').glob('*/work'))


@pytest.mark.parametrize('problem, message', [
    ('missing', '--project tvc --no-upload'), ('identity', 'mismatched'),
    ('bounds', 'geographic bounds'), ('checksum', 'pinned CanSWE v8'),
    ('licence', 'Hydro-Quebec'), ('empty', 'No stations found'),
])
def test_incomplete_or_invalid_selection_preserves_existing_bundle(regional_source, regional_site, tmp_path, capsys, problem, message):
    catalogue = tmp_path / 'staging/data/tvc/catalog.json'
    data = json.loads(catalogue.read_text())
    if problem == 'missing':
        catalogue.unlink()
    elif problem == 'identity':
        data['domain']['id'] = 'other'
    elif problem == 'bounds':
        data['bounds'] = [-134, 68, float('nan'), 70]
    elif problem == 'checksum':
        regional_source.write_bytes(b'wrong release')
    elif problem == 'licence':
        data['bounds'] = [-80, 45, -60, 60]
    elif problem == 'empty':
        data['bounds'] = [-160, 80, -150, 85]
        raw = json.loads(regional_site.read_text()); raw['projects'] = [raw['projects'][1]]
        regional_site.write_text(json.dumps(raw))
    if problem != 'missing':
        catalogue.write_text(json.dumps(data))
    bundle = tmp_path / 'existing.zip'; bundle.write_bytes(b'keep previous bundle')
    assert main(['site', 'prepare-canswe', str(regional_site), '--source', str(regional_source), '--bundle', str(bundle)]) == 1
    assert message in capsys.readouterr().err
    assert bundle.read_bytes() == b'keep previous bundle'


def test_interrupted_pack_preserves_previous_bundle(regional_source, regional_site, tmp_path, monkeypatch):
    bundle = tmp_path / 'existing.zip'; bundle.write_bytes(b'previous')
    def fail_write(*args, **kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(zipfile.ZipFile, 'writestr', fail_write)
    with pytest.raises(OSError, match='disk full'):
        canswe.prepare_site_bundle(load_site(regional_site), regional_source, bundle)
    assert bundle.read_bytes() == b'previous'
    assert not list(tmp_path.glob('.existing.zip.*.tmp'))
