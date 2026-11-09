from datetime import datetime, timedelta, timezone
import json

from postprocess.publish_cogs import retained_times, publish
from test_publish_cogs import write


def times(start, count):
    day = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    return [(day + timedelta(days=i)).strftime("%Y-%m-%dT23:00:00Z") for i in range(count)]


def test_year_retention_has_ten_daily_dates_and_stable_weekly_snapshots():
    stamps = times("2025-11-01", 375)
    latest = datetime.fromisoformat(stamps[-1])
    selected = retained_times(stamps, latest, 10)
    assert set(stamps[-10:]) <= selected
    older = selected - set(stamps[-10:])
    assert all(datetime.fromisoformat(t).weekday() == 6 for t in older)
    assert len(selected) <= 62
    assert min(selected) >= (latest - timedelta(days=364)).date().isoformat()
    # Once a week has ended its chosen snapshot does not slide with the cutoff.
    next_latest = latest + timedelta(days=1)
    again = retained_times([*stamps, next_latest.isoformat().replace('+00:00', 'Z')], next_latest, 10)
    assert older - {min(older)} <= again


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
    assert json.loads((output / 'catalog.json').read_text())['retention']['weekly_days'] == 365
