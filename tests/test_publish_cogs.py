import importlib.util
import json
import os
from pathlib import Path
import stat

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

spec = importlib.util.spec_from_file_location("publisher", Path(__file__).parents[1] / "postprocess/publish_cogs.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def write(folder, date="20261105T230000", value=125, variable="swe", crs="EPSG:4326", dtype="float32", nodata=-9999,
          grid="0.001x0.001", transform=None):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{variable}-{grid}_{date}.tiff"
    dx, dy = map(float, grid.split("x"))
    data = np.full((600, 600), value, dtype=dtype)
    data[0, 0] = nodata
    with rasterio.open(path, "w", driver="GTiff", width=600, height=600, count=1,
                       dtype=dtype, nodata=nodata, crs=crs,
                       transform=transform or from_origin(-116, 52, dx, dy)) as dst:
        dst.write(data, 1)
        dst.scales = (.1,); dst.offsets = (2,)
    return path


def test_numeric_values_georeferencing_mask_and_scale_survive(tmp_path):
    source = write(tmp_path / "input")
    catalogue = publisher.publish([source.parent], tmp_path / "published")
    asset = catalogue["variables"][0]["assets"][0]
    with rasterio.open(source) as src, rasterio.open(tmp_path / "published" / asset["path"]) as cog:
        np.testing.assert_array_equal(src.read(1), cog.read(1))
        np.testing.assert_array_equal(src.read_masks(1), cog.read_masks(1))
        assert cog.transform == src.transform and cog.crs == src.crs
        assert cog.scales == src.scales and cog.offsets == src.offsets
        assert cog.tags(ns="IMAGE_STRUCTURE")["LAYOUT"] == "COG"
        assert cog.overviews(1)
    assert asset["scale"] == .1 and asset["offset"] == 2


def test_window_merges_existing_publication_and_keeps_missing_days(tmp_path):
    src = tmp_path / "input"; dst = tmp_path / "published"
    first = write(src, "20261027T230000")
    publisher.publish([src], dst)
    first.unlink()
    write(src, "20261105T230000")
    c = publisher.publish([src], dst)
    assert len(c["variables"][0]["assets"]) == 2
    write(src, "20261106T230000")
    c = publisher.publish([src], dst)
    assert all(a["datetime"] >= "2026-10-28" for a in c["variables"][0]["assets"])


def test_revision_has_new_url_and_idempotent_republish(tmp_path):
    src = tmp_path / "input"; dst = tmp_path / "published"
    write(src)
    old = publisher.publish([src], dst)["variables"][0]["assets"][0]
    same = publisher.publish([src], dst)["variables"][0]["assets"][0]
    assert old["href"] == same["href"]
    write(src, value=225)
    new = publisher.publish([src], dst)["variables"][0]["assets"][0]
    assert old["href"] != new["href"]
    assert (dst / old["path"]).exists()


def test_failed_conversion_leaves_previous_catalogue_valid(tmp_path):
    src = tmp_path / "input"; dst = tmp_path / "published"
    write(src); publisher.publish([src], dst)
    previous = (dst / "catalog.json").read_bytes()
    write(src, "20261106T230000", crs=None)
    with pytest.raises(ValueError): publisher.publish([src], dst)
    assert (dst / "catalog.json").read_bytes() == previous


def test_current_directory_overrides_archive_and_external_base_url(tmp_path):
    write(tmp_path / "archive", value=1); write(tmp_path / "current", value=2)
    c = publisher.publish([tmp_path / "archive", tmp_path / "current"], tmp_path / "published", base_url="https://data.example/cogs/")
    asset = c["variables"][0]["assets"][0]
    assert asset["href"].startswith("https://data.example/cogs/cogs/")
    with rasterio.open(tmp_path / "published" / asset["path"]) as ds: assert ds.read(1)[1, 1] == 2


def test_missing_prior_asset_does_not_publish_broken_catalogue(tmp_path):
    src = tmp_path / "input"; dst = tmp_path / "published"
    source = write(src)
    c = publisher.publish([src], dst)
    source.unlink(); (dst / c["variables"][0]["assets"][0]["path"]).unlink()
    with pytest.raises(FileNotFoundError): publisher.publish([src], dst)


@pytest.mark.parametrize("variable,nodata", [("swe", -9999), ("snowdepthavg", float("nan")), ("t", -9999.1)])
def test_float64_is_cast_to_float32_without_changing_source_grid_or_mask(tmp_path, variable, nodata):
    source = write(tmp_path / "input", variable=variable, dtype="float64", nodata=nodata)
    values = np.linspace(-25.123456789, 450.987654321, 600 * 600).reshape(600, 600)
    values[0, 0] = nodata
    with rasterio.open(source, "r+") as src:
        src.write(values, 1)
        src.update_tags(1, units="test units")
    original = source.read_bytes()
    destination = tmp_path / "published"
    asset = publisher.publish([source.parent], destination)["variables"][0]["assets"][0]
    with rasterio.open(source) as src, rasterio.open(destination / asset["path"]) as cog:
        assert cog.dtypes == ("float32",)
        np.testing.assert_array_equal(cog.read(1), values.astype("float32"))
        np.testing.assert_array_equal(cog.read_masks(1), src.read_masks(1))
        assert (cog.crs, cog.transform, cog.shape) == (src.crs, src.transform, src.shape)
        assert cog.scales == src.scales and cog.offsets == src.offsets
        assert cog.tags(1)["units"] == "test units"
        assert cog.overviews(1)
        if np.isnan(nodata):
            assert np.isnan(cog.nodata) and asset["nodata"] == "NaN"
        else:
            assert cog.nodata == float(np.float32(nodata)) == asset["nodata"]
    assert asset["dtype"] == "float32" and asset["cog_encoding"] == publisher.COG_ENCODING
    assert source.read_bytes() == original
    assert not list(destination.rglob("*.source.vrt")) and not list(destination.rglob("*.partial.tif"))


def test_float32_conversion_preserves_an_explicit_mask(tmp_path):
    source = write(tmp_path / "input", dtype="float64")
    mask = np.full((600, 600), 255, dtype="uint8"); mask[:100, :100] = 0
    with rasterio.open(source, "r+") as src:
        src.write_mask(mask)
    destination = tmp_path / "converted.tif"
    publisher.convert(source, destination)
    with rasterio.open(destination) as cog:
        np.testing.assert_array_equal(cog.read_masks(1), mask)


def test_old_encoding_is_migrated_once_with_a_new_immutable_url(tmp_path):
    source = write(tmp_path / "input", dtype="float64")
    dst = tmp_path / "published"
    c = publisher.publish([source.parent], dst)
    old = c["variables"][0]["assets"][0]
    (dst / old["path"]).unlink()
    old["id"] = "legacy"; old["path"] = "cogs/swe/legacy.tif"; old["href"] = old["path"]
    old.pop("cog_encoding"); old.pop("dtype")
    publisher.raster_copy(source, dst / old["path"], driver="COG")
    old_bytes = (dst / old["path"]).read_bytes()
    publisher.atomic_json(dst / "catalog.json", c)
    new = publisher.publish([source.parent], dst)["variables"][0]["assets"][0]
    assert new["id"] != old["id"] and new["path"] != old["path"]
    assert new["source_sha256"] == old["source_sha256"]
    assert (dst / old["path"]).read_bytes() == old_bytes
    mtime = (dst / new["path"]).stat().st_mtime_ns
    same = publisher.publish([source.parent], dst)["variables"][0]["assets"][0]
    assert new == same and (dst / same["path"]).stat().st_mtime_ns == mtime


def test_failed_float32_conversion_does_not_switch_catalogue(tmp_path):
    src = tmp_path / "input"; dst = tmp_path / "published"
    write(src); publisher.publish([src], dst)
    previous = (dst / "catalog.json").read_bytes()
    write(src, "20261106T230000", dtype="float64", nodata=-1e100)
    with pytest.raises(ValueError, match="Float32 range"):
        publisher.publish([src], dst)
    assert (dst / "catalog.json").read_bytes() == previous


@pytest.mark.parametrize("previous_mode", [None, 0o600, 0o644])
def test_catalogue_is_publicly_readable_before_atomic_replacement(tmp_path, monkeypatch, previous_mode):
    path = tmp_path / "catalog.json"
    if previous_mode is not None:
        path.write_text('{"old": true}')
        path.chmod(previous_mode)
    replace = os.replace

    def check_mode(source, destination):
        assert stat.S_IMODE(Path(source).stat().st_mode) == 0o644
        assert json.loads(Path(source).read_text()) == {"ready": True}
        replace(source, destination)

    monkeypatch.setattr(publisher.os, "replace", check_mode)
    old_umask = os.umask(0o077)
    try:
        publisher.atomic_json(path, {"ready": True})
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_mixed_archive_and_current_inputs_only_publish_the_target_grid(tmp_path):
    archive, current = tmp_path / "archive", tmp_path / "current"
    write(archive, value=10)
    write(archive, value=100, grid="0.01x0.01")
    # A later directory must not replace a fine archive date with a coarse file.
    write(current, value=200, grid="0.01x0.01")
    write(current, "20261106T230000", value=20)
    write(current, "20261201T230000", grid="0.01x0.01")
    output = tmp_path / "published"
    catalogue = publisher.publish([archive, current], output)
    assert catalogue["latest_time"] == "2026-11-06T23:00:00Z"
    assert catalogue["grid"] == "0.001x0.001"
    values = []
    for asset in catalogue["variables"][0]["assets"]:
        with rasterio.open(output / asset["path"]) as cog:
            assert cog.res == (.001, .001)
            values.append(cog.read(1)[1, 1])
    assert values == [10, 20]


def test_migrates_a_mixed_legacy_catalogue_without_retaining_coarse_dates(tmp_path):
    source = write(tmp_path / "fine", "20261104T230000")
    output = tmp_path / "published"
    legacy = publisher.publish([source.parent], output)
    source.unlink()  # Retain a fine-grid date whose original has expired.
    coarse = tmp_path / "coarse"
    write(coarse, "20261105T230000", grid="0.01x0.01")
    write(coarse, "20261106T230000", grid="0.01x0.01")
    with pytest.warns(UserWarning, match="Omitting"):
        coarse_catalogue = publisher.publish([coarse], output, grid="0.01x0.01")
    legacy["variables"][0]["assets"] += coarse_catalogue["variables"][0]["assets"]
    legacy.pop("grid")
    publisher.atomic_json(output / "catalog.json", legacy)
    write(source.parent, "20261106T230000", value=60)
    with pytest.warns(UserWarning, match="Omitting 2"):
        catalogue = publisher.publish([coarse, source.parent], output)
    assets = catalogue["variables"][0]["assets"]
    assert [a["datetime"] for a in assets] == ["2026-11-04T23:00:00Z", "2026-11-06T23:00:00Z"]
    assert all(a["transform"][0] == .001 for a in assets)
    with rasterio.open(output / assets[-1]["path"]) as cog:
        assert cog.read(1)[1, 1] == 60


@pytest.mark.parametrize("change", ["origin", "projection", "shape"])
def test_unaligned_dates_leave_the_previous_catalogue_untouched(tmp_path, change):
    source = write(tmp_path / "input")
    output = tmp_path / "published"
    publisher.publish([source.parent], output)
    previous = (output / "catalog.json").read_bytes()
    revised = write(source.parent, "20261106T230000")
    if change == "shape":
        with rasterio.open(revised) as src:
            profile = src.profile
            data = src.read(1)[:-1]
        profile["height"] -= 1
        with rasterio.open(revised, "w", **profile) as dst:
            dst.write(data, 1)
    else:
        with rasterio.open(revised, "r+") as src:
            if change == "origin":
                src.transform = from_origin(-115.9995, 52, .001, .001)
            else:
                src.crs = "EPSG:3857"
    with pytest.raises(ValueError, match="Unaligned swe grids"):
        publisher.publish([source.parent], output)
    assert (output / "catalog.json").read_bytes() == previous


def test_mislabelled_resolution_is_rejected(tmp_path):
    source = write(tmp_path / "input", transform=from_origin(-116, 52, .01, .01))
    output = tmp_path / "published"
    with pytest.raises(ValueError, match="resolution does not match"):
        publisher.publish([source.parent], output)
    assert not (output / "catalog.json").exists()


def test_nominal_grid_accepts_live_export_spacing_but_preserves_actual_georeferencing(tmp_path):
    # Actual grid spacing from the deployed catalogue: integer raster dimensions
    # make the cell sizes slightly different from the filename's nominal 0.001.
    transform = from_origin(-131.99520251328192, 55.998066919723286,
                            .0010000196336432264, .00100005429524892)
    source = write(tmp_path / "input", transform=transform)
    output = tmp_path / "published"
    publisher.publish([source.parent], output)
    source.unlink()
    write(source.parent, "20261106T230000", transform=transform)
    catalogue = publisher.publish([source.parent], output)
    assets = catalogue["variables"][0]["assets"]
    assert len(assets) == 2
    for asset in assets:
        assert asset["transform"] == list(transform)[:6]
        with rasterio.open(output / asset["path"]) as cog:
            assert cog.transform == transform


def test_coarse_only_inputs_require_explicit_grid_selection(tmp_path):
    source = write(tmp_path / "input", grid="0.01x0.01")
    output = tmp_path / "published"
    with pytest.raises(ValueError, match="found for grid 0.001x0.001"):
        publisher.publish([source.parent], output)
    assert not (output / "catalog.json").exists()
    catalogue = publisher.publish([source.parent], output, grid="0.01x0.01")
    assert catalogue["grid"] == "0.01x0.01"


def test_external_mask_addition_revision_and_removal_change_the_published_asset(tmp_path):
    source = write(tmp_path / "input")
    output = tmp_path / "published"
    tiff_digest = publisher.sha256(source)
    mask_path = Path(str(source) + ".msk")

    def publish_mask(expected):
        asset = publisher.publish([source.parent], output)["variables"][0]["assets"][0]
        with rasterio.open(output / asset["path"]) as cog:
            np.testing.assert_array_equal(cog.read_masks(1), expected)
        assert publisher.publish([source.parent], output)["variables"][0]["assets"][0] == asset
        return asset

    with rasterio.open(source) as src:
        original_mask = src.read_masks(1)
    original = publish_mask(original_mask)
    masks = []
    for start in (10, 20):
        mask = np.full((600, 600), 255, dtype="uint8")
        mask[start:start + 10, :30] = 0
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=False):
            with rasterio.open(source, "r+") as src:
                src.write_mask(mask)
        assert mask_path.is_file()
        assert publisher.sha256(source) == tiff_digest
        masks.append(publish_mask(mask))
    assert len({a["href"] for a in [original, *masks]}) == 3
    mask_path.unlink()
    restored = publish_mask(original_mask)
    assert restored["href"] == original["href"] != masks[-1]["href"]


def test_legacy_tiff_only_identity_is_rebuilt_with_dataset_dependencies(tmp_path):
    source = write(tmp_path / "input")
    output = tmp_path / "published"
    catalogue = publisher.publish([source.parent], output)
    catalogue["variables"][0]["assets"][0]["source_sha256"] = publisher.sha256(source)
    publisher.atomic_json(output / "catalog.json", catalogue)
    mask = np.zeros((600, 600), dtype="uint8")
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=False):
        with rasterio.open(source, "r+") as src:
            src.write_mask(mask)
    updated = publisher.publish([source.parent], output)["variables"][0]["assets"][0]
    assert updated["source_sha256"] != catalogue["variables"][0]["assets"][0]["source_sha256"]
    with rasterio.open(output / updated["path"]) as cog:
        np.testing.assert_array_equal(cog.read_masks(1), mask)


def test_auxiliary_metadata_and_directory_moves_are_part_of_dataset_identity(tmp_path):
    source = write(tmp_path / "current")
    output = tmp_path / "published"
    original = publisher.publish([source.parent], output)["variables"][0]["assets"][0]
    auxiliary = Path(str(source) + ".aux.xml")
    auxiliary.write_text('<PAMDataset><PAMRasterBand band="1"><Scale>0.5</Scale>'
                         '<Offset>10</Offset></PAMRasterBand></PAMDataset>')
    revised = publisher.publish([source.parent], output)["variables"][0]["assets"][0]
    assert revised["href"] != original["href"]
    assert (revised["scale"], revised["offset"]) == (.5, 10)
    with rasterio.open(output / revised["path"]) as cog:
        assert cog.scales == (.5,) and cog.offsets == (10,)
    archive = tmp_path / "archive"
    source.parent.rename(archive)
    assert publisher.publish([archive], output)["variables"][0]["assets"][0] == revised
