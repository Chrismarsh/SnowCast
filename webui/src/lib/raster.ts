import { fromUrl, type GeoTIFF } from 'geotiff';
import proj4 from 'proj4';
import { register } from 'ol/proj/proj4';
import { get as getProjection, transform } from 'ol/proj';
import type { Asset, PointValue } from './types';
import { physicalValue, pixelAt } from './data';

const files = new Map<string, Promise<GeoTIFF>>();
const values = new Map<string, number | null>();
const limit = 64;

export function ensureProjection(code: string, definition?: string): void {
  if (getProjection(code)) return;
  if (!proj4.defs(code)) {
    const epsg = Number(code.split(':')[1]);
    if (definition) proj4.defs(code, definition);
    else if (epsg >= 32601 && epsg <= 32660) proj4.defs(code, `+proj=utm +zone=${epsg - 32600} +datum=WGS84 +units=m +no_defs`);
    else if (epsg >= 32701 && epsg <= 32760) proj4.defs(code, `+proj=utm +zone=${epsg - 32700} +south +datum=WGS84 +units=m +no_defs`);
    else throw new Error(`Unsupported CRS ${code}; publish it with a PROJ definition in the catalogue.`);
  }
  register(proj4);
}

async function open(url: string): Promise<GeoTIFF> {
  let item = files.get(url);
  if (!item) {
    item = fromUrl(url, { allowFullFile: false }, AbortSignal.timeout(30000));
    files.set(url, item);
    if (files.size > limit) files.delete(files.keys().next().value!);
  }
  try { return await item; } catch (e) { files.delete(url); throw e; }
}

export async function sample(asset: Asset, lonlat: number[], signal?: AbortSignal): Promise<number | null> {
  signal?.throwIfAborted();
  ensureProjection(asset.projection, asset.proj4);
  const pixel = pixelAt(transform(lonlat, 'EPSG:4326', asset.projection), asset.transform, asset.shape);
  if (!pixel) return null;
  const cacheKey = `${asset.href}:${pixel.join(',')}`;
  if (values.has(cacheKey)) return values.get(cacheKey)!;
  const tiff = await open(asset.href);
  const image = await tiff.getImage(0); // Always full resolution, independent of map zoom.
  const [x, y] = pixel;
  const window = [x, y, x + 1, y + 1];
  const raw = await image.readRasters({ window, samples: [0], interleave: true, signal });
  let value = physicalValue(Number(raw[0]), asset.nodata, asset.scale, asset.offset);
  // Honour a full-resolution TIFF mask, including datasets with no nodata sentinel.
  const count = await tiff.getImageCount();
  for (let i = 1; i < count; i++) {
    const mask = await tiff.getImage(i);
    const type = Number(await mask.getFileDirectory().loadValue('NewSubfileType') || 0);
    if ((type & 4) && mask.getWidth() === image.getWidth() && mask.getHeight() === image.getHeight()) {
      const valid = await mask.readRasters({ window, samples: [0], interleave: true, signal });
      if (!valid[0]) value = null;
      break;
    }
  }
  signal?.throwIfAborted();
  values.set(cacheKey, value);
  if (values.size > 2048) values.delete(values.keys().next().value!);
  return value;
}

export async function sampleSeries(assets: Asset[], lonlat: number[], signal: AbortSignal): Promise<PointValue[]> {
  const result: PointValue[] = new Array(assets.length);
  let cursor = 0;
  await Promise.all(Array.from({ length: Math.min(3, assets.length) }, async () => {
    while (cursor < assets.length) {
      signal.throwIfAborted();
      const index = cursor++;
      try { result[index] = { time: assets[index].datetime, value: await sample(assets[index], lonlat, signal) }; }
      catch (e) {
        if (signal.aborted) throw e;
        result[index] = { time: assets[index].datetime, value: null, error: e instanceof Error ? e.message : 'Raster read failed' };
      }
    }
  }));
  return result;
}
