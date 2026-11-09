from pathlib import Path

import numpy as np
import pytest
import rasterio

from postprocess.publish_cogs import dataset_sha256, publish
from test_publish_cogs import write
from webupload.upload import _rolling_copy


def test_rotation_preserves_dataset_identity_mask_and_pam_metadata(tmp_path):
    current, archive, output = (tmp_path / name for name in ('current', 'archive', 'output'))
    source = write(current)
    mask = np.full((600, 600), 255, dtype='uint8'); mask[:10, :30] = 0
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=False):
        with rasterio.open(source, 'r+') as dataset:
            dataset.write_mask(mask)
    Path(str(source) + '.aux.xml').write_text(
        '<PAMDataset><PAMRasterBand band="1"><Scale>0.5</Scale><Offset>10</Offset></PAMRasterBand></PAMDataset>')
    for day in (6, 7, 8):
        write(current, f'202611{day:02}T230000')
    before = publish([archive, current], output)['variables'][0]['assets'][0]
    digest = dataset_sha256(source)
    _rolling_copy(str(current / '*.tiff'), current, archive, ntokeep=3)
    assert len(list(current.glob('*.tiff'))) == 3
    moved = archive / source.name
    assert dataset_sha256(moved) == digest
    assert not source.exists()
    assert not Path(str(source) + '.msk').exists()
    assert not Path(str(source) + '.aux.xml').exists()
    with rasterio.open(moved) as dataset:
        np.testing.assert_array_equal(dataset.read_masks(1), mask)
        assert dataset.scales == (.5,) and dataset.offsets == (10,)
    assert publish([archive, current], output)['variables'][0]['assets'][0] == before


def test_kept_tiff_copies_sidecars_without_counting_them_as_dates(tmp_path):
    current, destination, archive = (tmp_path / name for name in ('current', 'kept', 'archive'))
    current.mkdir()
    for day in (5, 6, 7, 8):
        for variable in ('swe', 't'):
            name = f'{variable}-0.001x0.001_202611{day:02}T230000.tiff'
            for suffix in ('', '.msk', '.aux.xml', '.ovr'):
                (current / (name + suffix)).write_bytes((name + suffix).encode())
    _rolling_copy(str(current / '*.tiff'), destination, archive, ntokeep=3)
    assert len(list(archive.glob('*.tiff'))) == 2
    assert len(list(destination.glob('*.tiff'))) == 6
    for target in (archive, destination):
        for raster in target.glob('*.tiff'):
            for suffix in ('.msk', '.aux.xml', '.ovr'):
                assert Path(str(raster) + suffix).read_bytes() == (raster.name + suffix).encode()


def test_failed_archive_move_preserves_source_sidecars(tmp_path, monkeypatch):
    import shutil
    from webupload.upload import _transfer_dataset
    source, archive = tmp_path / 'source.tiff', tmp_path / 'archive'
    archive.mkdir()
    source.write_bytes(b'raster')
    sidecar = Path(str(source) + '.msk'); sidecar.write_bytes(b'mask')
    def fail(*args):
        raise OSError('transfer failed')
    monkeypatch.setattr(shutil, 'move', fail)
    with pytest.raises(OSError, match='transfer failed'):
        _transfer_dataset(source, archive, move=True)
    assert source.read_bytes() == b'raster' and sidecar.read_bytes() == b'mask'


def test_copy_does_not_inherit_old_destination_mask(tmp_path):
    from webupload.upload import _transfer_dataset
    source, destination = tmp_path / 'source.tiff', tmp_path / 'destination'
    destination.mkdir()
    source.write_bytes(b'revised unmasked raster')
    (destination / source.name).write_bytes(b'old raster')
    stale_mask = destination / (source.name + '.msk'); stale_mask.write_bytes(b'old mask')
    _transfer_dataset(source, destination)
    assert not stale_mask.exists()
    assert (destination / source.name).read_bytes() == source.read_bytes()
