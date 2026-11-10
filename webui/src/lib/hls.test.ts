import { describe, expect, it } from 'vitest';
import { compositeScene, hlsParams, hlsWindow, initialHls, parseScenes, sceneTileURL, sortScenes, validDay, type HlsScene } from './hls';

const sentinel: HlsScene = { id: 'S', collection: 'hls2-s30', datetime: '2026-11-09T18:00:00.000Z', platform: 'sentinel-2c', bounds: [-118, 49, -115, 52] };
const landsat: HlsScene = { ...sentinel, id: 'L', collection: 'hls2-l30', platform: 'landsat-9', datetime: '2026-11-10T18:00:00.000Z' };

describe('HLS observation dates and sharing', () => {
  it('uses an inclusive UTC lookback and never fetches observations after the selected date', () => {
    const settings = { ...initialHls(), days: 7 };
    expect(hlsWindow(settings, '2026-01-03')).toEqual({ start: '2025-12-28', end: '2026-01-03' });
    expect(hlsWindow({ ...settings, mode: 'date', date: '2026-01-01' }, '2026-01-03')).toEqual({ start: '2026-01-01', end: '2026-01-01' });
    expect(() => hlsWindow({ ...settings, mode: 'date', date: '2026-01-04' }, '2026-01-03')).toThrow();
    expect(validDay('2026-02-30')).toBe(false);
    expect(hlsWindow(settings, '2020-01-02').start).toBe('2020-01-01');
  });
  it('round-trips settings in shared URLs, keeps other options, and defaults off', () => {
    expect(initialHls().enabled).toBe(false);
    const settings = { ...initialHls(), enabled: true, view: 'snow' as const, opacity: 0, days: 14 };
    const params = new URLSearchParams('basemap=terrain&sat-date=2026-01-01');
    hlsParams(params, settings);
    expect(initialHls(params)).toEqual(settings);
    expect(params.get('basemap')).toBe('terrain');
    expect(params.has('sat-date')).toBe(false);
    hlsParams(params, { ...settings, enabled: false });
    expect(params.toString()).toBe('basemap=terrain');
    expect(initialHls(new URLSearchParams('satellite=1&sat-opacity=NaN&sat-days=999&sat-date=bad')).opacity).toBe(0.85);
  });
  it('rejects malformed and out-of-window catalogue data', () => {
    const window = { start: '2026-11-09', end: '2026-11-10' };
    const feature = { id: 'S', collection: 'hls2-s30', bbox: sentinel.bounds, properties: { datetime: sentinel.datetime } };
    expect(parseScenes([feature], window)[0].platform).toBe('Sentinel-2');
    expect(() => parseScenes([{ ...feature, properties: { datetime: '2026-11-11T00:00:00Z' } }], window)).toThrow('outside');
    expect(() => parseScenes([{ ...feature, collection: 'other' }], window)).toThrow('metadata');
    expect(() => parseScenes(null, window)).toThrow();
  });
});

describe('HLS rendering and provenance', () => {
  it('maps equivalent snow bands correctly and preserves snow while excluding clouds/shadows/fill', () => {
    for (const scene of [sentinel, landsat]) {
      const params = new URL(sceneTileURL(scene, 'snow', 10, 180, 347)).searchParams;
      expect(params.get('expression')).toContain(scene.collection === 'hls2-s30' ? 'B11;B8A;B04' : 'B06;B05;B04');
      expect(params.get('return_mask')).toBe('false');
      expect(params.getAll('rescale')).toEqual(['0,10000', '0,10000', '0,10000', '0,255']);
    }
    const expression = new URL(sceneTileURL(sentinel, 'true-color', 10, 180, 347)).searchParams.get('expression')!;
    expect(expression).toContain('B04;B03;B02;where(((Fmask % 16) < 2)');
    // Exact predicate used by the remote renderer: bit 4 is snow, not an exclusion.
    for (const qa of [0, 16, 32, 48, 80, 144]) expect(qa % 16 < 2).toBe(true);
    for (const qa of [2, 4, 8, 18, 20, 24, 255]) expect(qa % 16 < 2).toBe(false);
  });
  it('selects newest valid pixels across sensors and records the scene that actually supplied each pixel', () => {
    expect(sortScenes([sentinel, landsat, sentinel])).toEqual([landsat, sentinel]);
    const pixels = new Uint8ClampedArray(12), provenance = new Uint16Array(3);
    expect(compositeScene(pixels, provenance, new Uint8ClampedArray([80, 90, 100, 255, 0, 0, 0, 0, 0, 0, 0, 0]), 0)).toBe(1);
    expect(compositeScene(pixels, provenance, new Uint8ClampedArray([1, 2, 3, 255, 200, 210, 220, 255, 0, 0, 0, 0]), 1)).toBe(1);
    expect([...pixels]).toEqual([80, 90, 100, 255, 200, 210, 220, 255, 0, 0, 0, 0]);
    expect([...provenance]).toEqual([1, 2, 0]);
    expect(() => compositeScene(pixels, provenance, new Uint8ClampedArray(4), 2)).toThrow('dimensions');
  });
});
