import { describe, expect, it } from 'vitest';
import { displayPixelRatio, TileProgress } from './mapPerformance';

describe('display work budget', () => {
  it('bounds a high-DPI laptop viewport to four million display pixels', () => {
    const ratio = displayPixelRatio(2, [2048, 1200]);
    expect(2048 * 1200 * ratio ** 2).toBeLessThanOrEqual(4_000_001);
    expect(ratio).toBeLessThan(2);
  });
  it('keeps small viewports sharp and allows a lower-detail comparison', () => {
    expect(displayPixelRatio(3, [390, 600])).toBe(2);
    expect(displayPixelRatio(3, [390, 600], true)).toBe(1);
    expect(displayPixelRatio(1, [1200, 800])).toBe(1);
  });
});

describe('tile progress', () => {
  it('tracks overlapping loads, retries, and failures without negative pending counts', () => {
    const progress = new TileProgress(), a = {}, b = {};
    progress.start(a); progress.start(a); progress.start(b);
    progress.end(a, true);
    expect(progress.snapshot()).toMatchObject({ started: 2, pending: 1, settled: 1, errors: 1 });
    progress.start(a); progress.end(a); progress.end(b);
    expect(progress.snapshot()).toMatchObject({ started: 3, pending: 0, settled: 3, errors: 1 });
  });
});
