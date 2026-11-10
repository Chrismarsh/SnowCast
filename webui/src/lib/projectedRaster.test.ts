import { describe, expect, it, vi } from 'vitest';
import RasterSource from 'ol/source/Raster';
import ImageCanvas from 'ol/ImageCanvas';
import ImageState from 'ol/ImageState';
import { get as getProjection, transformExtent } from 'ol/proj';
import { ProjectedRaster } from './projectedRaster';

const native = getProjection('EPSG:4326')!;
const mercator = getProjection('EPSG:3857')!;
const bounds = [-132, 46, -110, 56];
const viewport = transformExtent(bounds, native, mercator);

function setup() {
  const raster = new RasterSource({ sources: [] });
  // Only the image metadata is needed: these tests exercise the real
  // OpenLayers reprojection requests without pretending to test canvas pixels.
  const canvas = { width: 220, height: 100 } as HTMLCanvasElement;
  const read = vi.spyOn(raster, 'getImage').mockImplementation((extent, resolution) =>
    new ImageCanvas(extent, resolution, 1, canvas));
  return { raster, read, source: new ProjectedRaster(raster, native) };
}

describe('Canvas image reprojection', () => {
  it('keeps a Mercator output while requesting numeric styling only in the native CRS', () => {
    const { read, source } = setup();
    const image = source.getImage(viewport, 10_000, 1, mercator)!;
    const [extent, resolution, , projection] = read.mock.calls[0];
    expect(projection.getCode()).toBe('EPSG:4326');
    extent.forEach((value, i) => expect(value).toBeCloseTo(bounds[i], 5));
    expect(resolution).toBeGreaterThan(0);
    expect(resolution).toBeLessThan(1);
    expect(image.getExtent()).toEqual(viewport);
    expect(image.getResolution()).toBe(10_000);
    expect(image.getState()).toBe(ImageState.IDLE);
    expect(source.frameReady).toBe(false); // native colouring alone is not completion
    source.dispose();
  });

  it('invalidates an empty result when native tiles arrive, and invalidates on pan', () => {
    const { raster, read, source } = setup();
    read.mockReturnValueOnce(null);
    const empty = source.getImage(viewport, 10_000, 1, mercator)!;
    expect(empty.getState()).toBe(ImageState.EMPTY);
    expect(source.frameReady).toBe(false);
    raster.changed();
    const loaded = source.getImage(viewport, 10_000, 1, mercator)!;
    expect(loaded).not.toBe(empty);
    expect(loaded.getState()).toBe(ImageState.IDLE);
    expect(source.getImage(viewport, 10_000, 1, mercator)).toBe(loaded);
    const panned = viewport.map((n, i) => n + (i % 2 === 0 ? 100_000 : 0));
    expect(source.getImage(panned, 10_000, 1, mercator)).not.toBe(loaded);
    expect(read).toHaveBeenCalledTimes(3);
    source.dispose();
  });

  it('accepts completed native images and releases the worker and change listener on disposal', () => {
    const { raster, source } = setup();
    const dispose = vi.spyOn(raster, 'dispose');
    source.getImage(bounds, 0.1, 1, native);
    expect(source.frameReady).toBe(true);
    raster.changed();
    expect(source.frameReady).toBe(false);
    source.dispose();
    expect(dispose).toHaveBeenCalledOnce();
    const revision = source.getRevision();
    raster.changed();
    expect(source.getRevision()).toBe(revision);
  });
});
