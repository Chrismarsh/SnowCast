import { afterAll, expect, it, vi } from 'vitest';
import DataTileSource from 'ol/source/DataTile';
import DataTile from 'ol/DataTile';
import RasterSource from 'ol/source/Raster';
import TileGrid from 'ol/tilegrid/TileGrid';
import { get as getProjection, transformExtent, fromLonLat } from 'ol/proj';
import { ProjectedRaster } from './projectedRaster';
import { colorPixel } from './data';
import { TileFailures } from './rasterRequests';
import * as canvas from '@napi-rs/canvas';

vi.stubGlobal('document', {createElement: (tag: string) => {
  if (tag !== 'canvas') throw new Error('Unexpected DOM element: ' + tag);
  const c = canvas.createCanvas(1, 1);
  const getContext = c.getContext.bind(c);
  return Object.assign(c, {style: {}, getContext: (type: string) => {
    if (type !== '2d') throw new Error('Compatibility mode attempted ' + type);
    return getContext('2d');
  }});
}});
vi.stubGlobal('ImageData', canvas.ImageData);
vi.stubGlobal('HTMLCanvasElement', canvas.createCanvas(1, 1).constructor);
vi.stubGlobal('HTMLImageElement', canvas.Image);
vi.stubGlobal('HTMLVideoElement', class {});
vi.stubGlobal('ImageBitmap', class {});
vi.stubGlobal('requestAnimationFrame', (callback: () => void) => setTimeout(callback, 0));
afterAll(() => vi.unstubAllGlobals());

it('renders masked numeric data into the correct Mercator positions using only Canvas 2D', async () => {
  const native = getProjection('EPSG:4326')!;
  const mercator = getProjection('EPSG:3857')!;
  const bounds = [-130, 45, -110, 65];
  const values = new Float32Array(256 * 256 * 2);
  for (let y = 0; y < 256; y++) for (let x = 0; x < 256; x++) {
    const i = (y * 256 + x) * 2;
    values[i] = x < 64 ? -9999 : x < 128 ? 0 : y < 128 ? -20 : 5;
    values[i + 1] = x < 64 ? 0 : 1;
  }
  const data = {colors: [[40,75,163], [249,202,153], [184,53,61]], min:-20, max:5, scale:1, offset:0, nodata:-9999};
  const numeric = new DataTileSource({projection:native, bandCount:2, tileSize:256,
    tileGrid: new TileGrid({extent:bounds, resolutions:[20/256], tileSize:256}), loader:()=>values});
  const getTile = vi.spyOn(numeric, 'getTile');
  const raster = new RasterSource({sources:[numeric], threads:0, operation:colorPixel});
  raster.on('beforeoperations', e => Object.assign(e.data, data));
  const source = new ProjectedRaster(raster, native);
  const extent = transformExtent(bounds, native, mercator);
  const resolution = (extent[2] - extent[0]) / 512;
  let image;
  try {
    await vi.waitFor(() => {
      image = source.getImage(extent, resolution, 1, mercator);
      image?.load();
      expect(source.frameReady).toBe(true);
    }, {timeout: 5000, interval: 10});
    const output = image!.getImage() as HTMLCanvasElement;
    expect(output.width).toBe(512);
    expect(output.height).toBeGreaterThan(800); // Mercator, not a square native grid
    for (const [lon,lat,raw,alpha] of [[-127,55,-9999,0],[-122,55,0,1],[-115,60,-20,1],[-115,50,5,1]]) {
      const point = fromLonLat([lon,lat]);
      const x = Math.floor((point[0]-extent[0])/resolution);
      const y = Math.floor((extent[3]-point[1])/resolution);
      const pixel = Array.from(output.getContext('2d')!.getImageData(x,y,1,1).data);
      const expected = new Uint8ClampedArray(colorPixel([[raw,alpha]],data));
      expect(pixel).toEqual(Array.from(expected));
    }
    expect(getTile.mock.calls.length).toBeGreaterThan(0);
    expect(getTile.mock.calls.every(call=>call[4]?.getCode()==='EPSG:4326')).toBe(true);
  } finally {source.dispose(); numeric.dispose();}
}, 10_000);

it('does not publish a transparent tile hole when a later pan fails, and renders after retry', async () => {
  const native = getProjection('EPSG:4326')!, mercator = getProjection('EPSG:3857')!;
  const failures = new TileFailures();
  let rejectEasternTile = true;
  let failedTile: DataTile | undefined;
  const values = new Float32Array(64 * 64 * 2);
  for (let i = 0; i < values.length; i += 2) { values[i] = 10; values[i + 1] = 1; }
  const numeric = new DataTileSource({ projection: native, bandCount: 2, tileSize: 64,
    tileGrid: new TileGrid({ extent: [-130, 50, -110, 60], resolutions: [10 / 64], tileSize: 64 }),
    loader: (_z, x) => {
      if (x === 1 && rejectEasternTile) throw new Error('Simulated later tile failure');
      return values;
    },
  });
  numeric.on('tileloadstart', e => failures.start(e.tile));
  numeric.on('tileloaderror', e => {
    failedTile = e.tile as DataTile;
    failures.error(e.tile, failedTile.getError());
  });
  const raster = new RasterSource({ sources: [numeric], threads: 0, operation: () => [40, 75, 163, 255] });
  const source = new ProjectedRaster(raster, native, () => failures.clear);
  const west = transformExtent([-129, 51, -121, 59], native, mercator);
  const both = transformExtent([-129, 51, -111, 59], native, mercator);
  const resolution = (both[2] - both[0]) / 256;
  const render = (extent: number[]) => {
    const image = source.getImage(extent, resolution, 1, mercator); image?.load(); return image;
  };
  try {
    await vi.waitFor(() => { render(west); expect(source.frameReady).toBe(true); });
    await vi.waitFor(() => { render(both); expect(failedTile).toBeDefined(); });
    expect(source.frameReady).toBe(false);
    expect(render(both)).toBeNull(); // Never hand the layer the partial image.
    rejectEasternTile = false;
    failedTile!.load();
    await vi.waitFor(() => { render(both); expect(source.frameReady).toBe(true); });
    const image = render(both)!.getImage() as HTMLCanvasElement;
    const p = fromLonLat([-115, 55]);
    expect(Array.from(image.getContext('2d')!.getImageData(
      Math.floor((p[0] - both[0]) / resolution), Math.floor((both[3] - p[1]) / resolution), 1, 1).data))
      .toEqual([40, 75, 163, 255]);
  } finally { source.dispose(); numeric.dispose(); }
});
