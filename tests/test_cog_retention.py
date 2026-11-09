from datetime import datetime, timedelta, timezone
import json

import pytest

from postprocess.publish_cogs import retained_times, publish
from test_publish_cogs import write


def times(start, count):
    day = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    return [(day + timedelta(days=i)).strftime("%Y-%m-%dT23:00:00Z") for i in range(count)]


def test_hydrological_year_has_ten_daily_dates_and_stable_weekly_snapshots():
    stamps = times("2025-11-01", 375)
    latest = datetime.fromisoformat(stamps[-1])
    selected = retained_times(stamps, latest, 10)
    assert set(stamps[-10:]) <= selected
    older = selected - set(stamps[-10:])
    assert all(datetime.fromisoformat(t).weekday() == 6 for t in older)
    assert len(selected) <= 62
    assert min(selected) >= '2026-09-01'
    # Once a week has ended its chosen snapshot does not slide with the cutoff.
    next_latest = latest + timedelta(days=1)
    again = retained_times([*stamps, next_latest.isoformat().replace('+00:00', 'Z')], next_latest, 10)
    assert older <= again


@pytest.mark.parametrize('latest_day,year_start', [
    ('2026-11-09', '2026-09-01'),
    ('2026-08-31', '2025-09-01'),
    ('2024-08-31', '2023-09-01'),  # Leap hydrological year has 366 days.
    ('2026-09-01', '2026-09-01'),
])
def test_september_boundary_excludes_previous_year_including_recent_daily_dates(latest_day, year_start):
    latest = datetime.fromisoformat(latest_day).replace(hour=23, tzinfo=timezone.utc)
    stamps = times((latest - timedelta(days=399)).date().isoformat(), 400)
    selected = retained_times(stamps, latest, 10)
    assert selected and min(selected) >= year_start
    assert {stamp for stamp in stamps[-10:] if stamp >= year_start} <= selected
    assert len(selected) <= 62
    if latest_day == year_start:
        assert selected == {stamps[-1]}


def test_leap_year_keeps_september_first_and_uses_model_date_not_wall_clock():
    stamps = ['2023-08-31T23:00:00Z', '2023-09-01T23:00:00Z', '2024-08-31T23:00:00Z']
    assert retained_times(stamps, datetime.fromisoformat(stamps[-1]), 10) == set(stamps[1:])


@pytest.mark.parametrize('weekly_days', [None, 0, 30, 365, 366])
def test_optional_history_caps_cannot_reintroduce_previous_hydrological_year(weekly_days):
    stamps = ['2026-08-31T23:00:00Z', '2026-09-01T23:00:00Z', '2026-09-05T23:00:00Z']
    assert retained_times(stamps, datetime.fromisoformat(stamps[-1]), 10, weekly_days) == set(stamps[1:])


def test_explicit_weekly_cap_can_shorten_current_year_history():
    stamps = ['2026-09-06T23:00:00Z', '2026-10-25T23:00:00Z', '2026-11-09T23:00:00Z']
    assert retained_times(stamps, datetime.fromisoformat(stamps[-1]), 10, 30) == set(stamps[1:])


def test_missing_sunday_uses_last_available_day_and_latest_time_of_that_day():
    stamps = ["2026-10-30T12:00:00Z", "2026-10-30T23:00:00Z", "2026-11-09T23:00:00Z"]
    selected = retained_times(stamps, datetime.fromisoformat(stamps[-1]), 10)
    assert selected == {stamps[1], stamps[2]}


def test_recent_missing_days_are_not_replaced_with_extra_old_daily_dates():
    stamps = times("2026-10-01", 40)
    available = stamps[:-2] + [stamps[-1]]
    selected = retained_times(available, datetime.fromisoformat(stamps[-1]), 10, 0)
    assert selected == set(stamps[-10:]) - {stamps[-2]}


def test_week_year_boundary_uses_calendar_weeks_not_week_number_alone():
    stamps = ["2025-12-31T23:00:00Z", "2026-01-04T23:00:00Z", "2026-01-19T23:00:00Z"]
    assert retained_times(stamps, datetime.fromisoformat(stamps[-1]), 10) == set(stamps[1:])


def test_publisher_archives_snow_only_and_skips_unselected_source_hashing(tmp_path, monkeypatch):
    source, output = tmp_path / 'input', tmp_path / 'output'
    for stamp in ("20261024T230000", "20261025T230000", "20261109T230000"):
        for variable in ("swe", "snowdepthavg", "t"):
            write(source, stamp, variable=variable)
    # Previous-year archives must be skipped before even opening the dataset.
    for variable in ("swe", "snowdepthavg", "t"):
        (source / f'{variable}-0.001x0.001_20260831T230000.tiff').write_bytes(b'not a readable TIFF')
    from postprocess import publish_cogs as publisher
    original = publisher.dataset_sha256
    hashed = []
    def digest(path):
        hashed.append(path.name)
        return original(path)
    monkeypatch.setattr(publisher, 'dataset_sha256', digest)
    catalogue = publish([source], output)
    groups = {v['id']: v['assets'] for v in catalogue['variables']}
    assert [a['datetime'] for a in groups['swe']] == ['2026-10-25T23:00:00Z', '2026-11-09T23:00:00Z']
    assert len(groups['snowdepthavg']) == 2 and len(groups['t']) == 1
    assert len(hashed) == 5 and not any('20261024' in name for name in hashed)
    assert catalogue['storage_bytes'] == sum((output / a['path']).stat().st_size for v in catalogue['variables'] for a in v['assets'])
    # Rotation of originals must not remove the weekly COG archive.
    for path in source.glob('*'):
        path.unlink()
    write(source, "20261110T230000")
    next_catalogue = publish([source], output)
    assert any(a['datetime'] == '2026-10-25T23:00:00Z' for a in next_catalogue['variables'][0]['assets'])
    retention = json.loads((output / 'catalog.json').read_text())['retention']
    assert retention['weekly_days'] is None
    assert retention['hydrological_year_start'] == '2026-09-01'


def test_september_rollover_drops_published_previous_year_and_cleans_after_grace(tmp_path, monkeypatch):
    from postprocess import publish_cogs as publisher
    source, output = tmp_path / 'input', tmp_path / 'output'
    for variable in ('swe', 'snowdepthavg', 't'):
        write(source, '20260831T230000', variable=variable)
    # Publication date must not select the hydrological year: the model date does.
    now = datetime(2026, 11, 9, tzinfo=timezone.utc)
    previous = publish([source], output, now=now)
    assert previous['retention']['hydrological_year_start'] == '2025-09-01'
    old_paths = [output / a['path'] for v in previous['variables'] for a in v['assets']]
    for variable in ('swe', 'snowdepthavg', 't'):
        write(source, '20260901T230000', variable=variable)
    digest = publisher.dataset_sha256
    hashed = []
    def record(path):
        hashed.append(path.name)
        return digest(path)
    monkeypatch.setattr(publisher, 'dataset_sha256', record)

    current = publish([source], output, now=now + timedelta(seconds=1))
    assert current['retention']['hydrological_year_start'] == '2026-09-01'
    assert current['window_days'] == 1  # No previous-year gap slots in the viewer.
    assert len(current['variables']) == 3
    assert all([a['datetime'] for a in v['assets']] == ['2026-09-01T23:00:00Z'] for v in current['variables'])
    assert len(hashed) == 3 and all('20260901' in name for name in hashed)
    assert all(path.exists() for path in old_paths)

    publish([source], output, now=now + timedelta(hours=48, seconds=1))
    assert all(not path.exists() for path in old_paths)
    assert len(list(source.glob('*.tiff'))) == 6  # Daily source archive is untouched.
