from pathlib import Path

import numpy as np
import pytest
import rasterio

from snowcast_runner.publish_cogs import dataset_sha256, publish
from snowcast_runner.project import load_project
from snowcast_runner.rasters import accept_exports, move_dataset
from snowcast_runner.state import workspace
from test_publish_cogs import write
from test_project_runner import project_file, change


def test_project_rotation_preserves_dataset_identity_mask_and_pam_metadata(project_file, tmp_path):
    change(project_file, lambda r: r.update(postprocess={'variables': ['swe']}))
    project = load_project(project_file)
    first, second = tmp_path / 'first', tmp_path / 'second'
    write(first)
    for day in (6, 7):
        write(second, f'202611{day:02}T230000')
    with workspace(project):
        accept_exports(project, first)
        current, archive = (project.work / 'postprocess' / name for name in ('tiff', 'archive_tiff'))
        source = next(current.glob('*.tiff'))
        # Adopt a compatible original TIFF without an internal mask, as a
        # migrated project can contain externally masked GDAL datasets.
        source.write_bytes((first / source.name).read_bytes())
        mask = np.full((600, 600), 255, dtype='uint8'); mask[:10, :30] = 0
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=False):
            with rasterio.open(source, 'r+') as dataset:
                dataset.write_mask(mask)
        assert Path(str(source) + '.msk').is_file()
        Path(str(source) + '.aux.xml').write_text(
            '<PAMDataset><PAMRasterBand band="1"><Scale>0.5</Scale><Offset>10</Offset></PAMRasterBand></PAMDataset>')
        output = tmp_path / 'published'
        before = publish([archive, current], output)['variables'][0]['assets'][0]
        digest = dataset_sha256(source)
        accept_exports(project, second)
        assert len(list(current.glob('*.tiff'))) == 2
        moved = archive / source.name
        assert dataset_sha256(moved) == digest
        assert not source.exists()
        assert not Path(str(source) + '.msk').exists()
        assert not Path(str(source) + '.aux.xml').exists()
        with rasterio.open(moved) as dataset:
            np.testing.assert_array_equal(dataset.read_masks(1), mask)
            assert dataset.scales == (.5,) and dataset.offsets == (10,)
        assert publish([archive, current], output)['variables'][0]['assets'][0] == before


def test_archive_moves_overviews_and_ascii_projection(tmp_path):
    source, destination = tmp_path / 'source.asc', tmp_path / 'archive'
    destination.mkdir()
    source.write_bytes(b'raster')
    source.with_suffix('.prj').write_bytes(b'projection')
    for suffix in ('.aux.xml', '.ovr', '.ovr.aux.xml'):
        Path(str(source) + suffix).write_bytes(suffix.encode())
    move_dataset(source, destination)
    assert not source.exists()
    assert not source.with_suffix('.prj').exists()
    assert (destination / 'source.prj').read_bytes() == b'projection'
    for suffix in ('.aux.xml', '.ovr', '.ovr.aux.xml'):
        assert not Path(str(source) + suffix).exists()
        assert (destination / (source.name + suffix)).read_bytes() == suffix.encode()


def test_failed_archive_move_preserves_source_sidecars(tmp_path, monkeypatch):
    source, archive = tmp_path / 'source.tiff', tmp_path / 'archive'
    archive.mkdir()
    source.write_bytes(b'raster')
    sidecar = Path(str(source) + '.msk'); sidecar.write_bytes(b'mask')
    def fail(*args):
        raise OSError('transfer failed')
    monkeypatch.setattr(Path, 'replace', fail)
    with pytest.raises(OSError, match='transfer failed'):
        move_dataset(source, archive)
    assert source.read_bytes() == b'raster' and sidecar.read_bytes() == b'mask'


def test_revision_does_not_inherit_old_archive_mask(tmp_path):
    source, destination = tmp_path / 'source.tiff', tmp_path / 'destination'
    destination.mkdir()
    source.write_bytes(b'revised unmasked raster')
    (destination / source.name).write_bytes(b'old raster')
    stale_mask = destination / (source.name + '.msk'); stale_mask.write_bytes(b'old mask')
    move_dataset(source, destination)
    assert not stale_mask.exists()
    assert not source.exists()
    assert (destination / source.name).read_bytes() == b'revised unmasked raster'
