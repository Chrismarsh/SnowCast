import { expect, it, vi } from 'vitest';
import DataTileSource from 'ol/source/DataTile';
import TileGrid from 'ol/tilegrid/TileGrid';
import TileState from 'ol/TileState';
import GeoTIFF from 'ol/source/GeoTIFF';
import { writeArrayBuffer } from 'geotiff';
import { DifferenceSource } from './differenceSource';
import type { Asset } from './types';

const asset: Asset = { id: 'test', href: '', datetime: '2026-11-07T00:00:00Z', projection: 'EPSG:4326', bounds: [-130, 50, -128, 52], shape: [2, 2], transform: [1, 0, -130, 0, -1, 52], nodata: -9999, scale: 1, offset: 0 };
function source(loader: () => Float32Array | Promise<Float32Array>) {
  const grid = new TileGrid({ extent: asset.bounds, resolutions: [1], tileSize: 2 });
  const s = new DataTileSource({ projection: asset.projection, bandCount: 2, tileSize: 2, tileGrid: grid, loader });
  vi.spyOn(s, 'getView').mockResolvedValue({ projection: asset.projection, extent: asset.bounds });
  return s;
}
const a = new Float32Array([10, 255, 0, 255, 99, 0, 5, 255]);
const b = new Float32Array([4, 255, 0, 255, 6, 255, 6, 0]);

it('reports a source metadata error even when its view promise never settles', async () => {
  const a = source(() => b);
  vi.spyOn(a, 'getView').mockReturnValue(new Promise(() => {}));
  const s = new DifferenceSource(a, source(() => b), asset, asset, new AbortController().signal);
  try {
    a.setState('error');
    await expect(s.getView()).rejects.toThrow('could not be opened');
    expect(s.getState()).toBe('error');
  } finally { s.dispose(); }
});

it('loads both dates as native numeric tiles, retaining signed and zero changes and both masks', async () => {
  const s = new DifferenceSource(source(() => a), source(() => b), asset, asset, new AbortController().signal);
  try {
    await s.getView();
    const tile = s.getTile(0, 0, 0, 1)!; tile.load();
    await vi.waitFor(() => expect(tile.getState()).toBe(TileState.LOADED));
    expect(Array.from(tile.getData() as Float32Array)).toEqual([-6, 255, 0, 255, 0, 0, 0, 0]);
    tile.dispose();
  } finally { s.dispose(); }
});

it('fails the whole comparison on a failed input and succeeds when the tile is retried', async () => {
  let fail = true;
  const s = new DifferenceSource(source(() => a), source(() => { if (fail) throw new Error('HTTP failure'); return b; }), asset, asset, new AbortController().signal);
  try {
    await s.getView(); const tile = s.getTile(0, 0, 0, 1)!; tile.load();
    await vi.waitFor(() => expect(tile.getState()).toBe(TileState.ERROR));
    expect(String(tile.getError())).toContain('HTTP failure');
    fail = false; tile.load();
    await vi.waitFor(() => expect(tile.getState()).toBe(TileState.LOADED));
    expect((tile.getData() as Float32Array)[0]).toBe(-6); tile.dispose();
  } finally { s.dispose(); }
});

it('cancels pending comparison tiles when their frame is discarded', async () => {
  const controller = new AbortController();
  const s = new DifferenceSource(source(() => new Promise(() => {})), source(() => b), asset, asset, controller.signal);
  try {
    await s.getView(); const tile = s.getTile(0, 0, 0, 1)!; tile.load();
    controller.abort();
    await vi.waitFor(() => expect(tile.getState()).toBe(TileState.ERROR)); tile.dispose();
  } finally { s.dispose(); }
});

it('reads and subtracts real GeoTIFF sources with independent nodata metadata', async () => {
  function cog(values: number[]) {
    const buffer = writeArrayBuffer(new Float32Array(values), { width: 2, height: 2,
      BitsPerSample: [32], SampleFormat: [3], SamplesPerPixel: 1,
      ModelPixelScale: [1, 1, 0], ModelTiepoint: [0, 0, 0, -130, 52, 0], GeographicTypeGeoKey: 4326 });
    return new GeoTIFF({ normalize: false, interpolate: false, projection: asset.projection,
      sourceOptions: { allowFullFile: true }, sources: [{ url: 'https://example.test/fixture.tif',
        loader: async () => new Response(buffer), bands: [1], nodata: -9999 }] });
  }
  const s = new DifferenceSource(cog([10, 0, -9999, 5]), cog([4, 0, 6, -9999]), asset, asset, new AbortController().signal);
  try {
    await s.getView();
    const z = s.getTileGrid()!.getMaxZoom(), tile = s.getTile(z, 0, 0, 1)!; tile.load();
    await vi.waitFor(() => expect(tile.getState()).toBe(TileState.LOADED));
    expect(Array.from(tile.getData() as Float32Array).slice(0, 8)).toEqual([-6, 255, 0, 255, 0, 0, 0, 0]); tile.dispose();
  } finally { s.dispose(); }
});
