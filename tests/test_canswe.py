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


@pytest.fixture
def regional_source(tmp_path, monkeypatch):
    """Tiny real NetCDF: two domains, overlap, boundaries and excluded stations."""
    from netCDF4 import Dataset
    source = tmp_path / 'observations.nc'
    points = [('west', -115, 51), ('tvc', -133.5, 68.75), ('gap', -125, 60),
              ('outside', -100, 45), ('edge', -134, 68), ('HQ-test', -72, 50), ('near-tvc', -133.5, 67.7)]
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


def test_spherical_distance_handles_arctic_longitude_and_corners():
    b = [-134, 68.58401629082839, -132.8927383062496, 68.96001629082839]
    assert canswe.distance_to_bounds(b, -133.5, 68.75) == 0
    assert canswe.distance_to_bounds(b, -133.53334045410156, 68.31666564941406) == pytest.approx(29.728, abs=.001)
    # At Arctic latitudes longitude degrees are far shorter than latitude degrees.
    assert 39 < canswe.distance_to_bounds(b, -131.8927383062496, 68.7) < 41
    assert canswe.distance_to_bounds([0, 0, 1, 1], 1.7, 1.7) > 100  # Beyond a circular corner buffer.


def test_converter_preserves_science_and_nearby_selection(regional_source, tmp_path):
    from snowcast_runner.observation_data import load_registry
    entry = load_registry()['datasets'][0]
    entry['source']['checksum'] = 'md5:' + hashlib.md5(regional_source.read_bytes()).hexdigest()
    domains = [{'id': 'west', 'name': 'West', 'bounds': [-132, 46.4, -109.8, 56]},
               {'id': 'tvc', 'name': 'TVC', 'bounds': [-134, 68, -132, 70]}]
    index = canswe.prepare(regional_source, tmp_path / 'out', domains=domains, entry=entry)
    assert {s['id'] for s in index['stations']} == {'west', 'tvc', 'edge', 'near-tvc'}
    assert index['domains'] == domains and index['nearby_km'] == 100
    for station in index['stations']:
        detail = json.loads(gzip.decompress((tmp_path / 'out' / station['href']).read_bytes()))
        assert detail['records'][0][1] == 0
        assert len(detail['seasonal']['swe']) == 24
        assert all(b['median'] is None for b in detail['seasonal']['swe'])
    entry['selection']['nearby_km'] = 0
    index = canswe.prepare(regional_source, tmp_path / 'inside', domains=domains, entry=entry)
    assert {s['id'] for s in index['stations']} == {'west', 'tvc', 'edge'}
    domains[0]['bounds'] = [-80, 45, -60, 60]
    with pytest.raises(ValueError, match='Hydro-Quebec'):
        canswe.prepare(regional_source, tmp_path / 'invalid', domains=domains, entry=entry)
