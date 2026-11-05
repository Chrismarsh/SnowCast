import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

spec = importlib.util.spec_from_file_location("publisher", Path(__file__).parents[1] / "postprocess/publish_cogs.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def write(folder, date="20261105T230000", value=125, variable="swe", crs="EPSG:4326"):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{variable}-0.001x0.001_{date}.tiff"
    data = np.full((600, 600), value, dtype="float32")
    data[0, 0] = -9999
    with rasterio.open(path, "w", driver="GTiff", width=600, height=600, count=1,
                       dtype="float32", nodata=-9999, crs=crs,
                       transform=from_origin(-116, 52, .001, .001)) as dst:
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
