import gzip
import importlib.util
import json
from pathlib import Path
import zipfile

import numpy as np
import pytest


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / 'scripts' / f'{name}.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


canswe = module('prepare_canswe')
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
    assert len(index['stations']) == 750
    assert len({s['id'] for s in index['stations']}) == 750
    assert index['dataset']['source_md5'] == canswe.SOURCE_MD5
    for station in index['stations']:
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
