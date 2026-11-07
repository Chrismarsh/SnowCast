import { expect, it, vi } from 'vitest';
import DataTileSource from 'ol/source/DataTile';
import TileGrid from 'ol/tilegrid/TileGrid';
import TileState from 'ol/TileState';
import GeoTIFF from 'ol/source/GeoTIFF';
import { writeArrayBuffer } from 'geotiff';
import { DifferenceSource } from './differenceSource';
import type { Asset } from './types';

const asset: Asset = { id: 'test', href: '', datetime: '2026-11-07T00:00:00Z', projection: 'EPSG:4326', bounds: [-130, 50, -128, 52], shape: [2, 2], transform: [1, 0, -130, 0, -1, 52], nodata: -9999, scale: 1, offset: 0 };
function source(loader: () => Float32Array | Promise<Float32Array>, renderedTileSize: number | number[] = 2, dataTileSize = 2) {
  const grid = new TileGrid({ extent: asset.bounds, resolutions: [1], tileSize: renderedTileSize });
  const s = new DataTileSource({ projection: asset.projection, bandCount: 2, tileSize: dataTileSize, tileGrid: grid, loader });
  vi.spyOn(s, 'getView').mockResolvedValue({ projection: asset.projection, extent: asset.bounds });
  return s;
}
const a = new Float32Array([10, 255, 0, 255, 99, 0, 5, 255]);
const b = new Float32Array([4, 255, 0, 255, 6, 255, 6, 0]);

function cog(values: number[], metadata = asset) {
  const buffer = writeArrayBuffer(new Float32Array(values), { width: 2, height: 2,
    BitsPerSample: [32], SampleFormat: [3], SamplesPerPixel: 1,
    ModelPixelScale: [metadata.transform[0], -metadata.transform[4], 0],
    ModelTiepoint: [0, 0, 0, metadata.transform[2], metadata.transform[5], 0], GeographicTypeGeoKey: 4326 });
  return new GeoTIFF({ normalize: false, interpolate: false, projection: metadata.projection,
    sourceOptions: { allowFullFile: true }, sources: [{ url: 'https://example.test/fixture.tif',
      loader: async () => new Response(buffer), bands: [1], nodata: -9999 }] });
}

it('accepts GeoTIFF display-tile rounding from the November 5 and 7 export scales', async () => {
  function metadata(dx: number): Asset {
    const dy = 0.00100005429524892, x = -131.99520251328192, y = 55.998066919723286;
    return { ...asset, bounds: [x, y - 2 * dy, x + 2 * dx, y], transform: [dx, 0, x, 0, -dy, y] };
  }
  const from = metadata(0.0010000196336432264), to = metadata(0.0010000196336434897);
  const a = cog([10, 0, -9999, 5], from), b = cog([4, 0, 6, -9999], to);
  const s = new DifferenceSource(a, b, from, to, new AbortController().signal);
  try {
    await Promise.all([a.getView(), b.getView()]);
    expect(a.getTileGrid()!.getTileSize(0)).not.toEqual(b.getTileGrid()!.getTileSize(0));
    await s.getView();
    const tile = s.getTile(s.getTileGrid()!.getMaxZoom(), 0, 0, 1)!; tile.load();
    await vi.waitFor(() => expect(tile.getState()).toBe(TileState.LOADED));
    expect(Array.from(tile.getData() as Float32Array)).toEqual([-6, 255, 0, 255, 0, 0, 0, 0]); tile.dispose();
  } finally { s.dispose(); }
});

it.each([
  { rendered: [2, 2.01], data: 2, message: 'tile grids' },
  { rendered: [2, 2], data: 3, message: 'tile sizes' },
])('still rejects incompatible $message', async ({ rendered, data, message }) => {
  const s = new DifferenceSource(source(() => a), source(() => b, rendered, data), asset, asset, new AbortController().signal);
  try { await expect(s.getView()).rejects.toThrow(message); }
  finally { s.dispose(); }
});

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
  const s = new DifferenceSource(cog([10, 0, -9999, 5]), cog([4, 0, 6, -9999]), asset, asset, new AbortController().signal);
  try {
    await s.getView();
    const z = s.getTileGrid()!.getMaxZoom(), tile = s.getTile(z, 0, 0, 1)!; tile.load();
    await vi.waitFor(() => expect(tile.getState()).toBe(TileState.LOADED));
    expect(Array.from(tile.getData() as Float32Array).slice(0, 8)).toEqual([-6, 255, 0, 255, 0, 0, 0, 0]); tile.dispose();
  } finally { s.dispose(); }
});
