import { expect, it } from 'vitest';
import { assertAligned, differenceAsset, differenceCSV, differenceVariable, pointDifference } from './difference';
import { subtractTiles } from './differenceSource';
import type { Asset, Variable } from './types';

const from: Asset = { id: 'a', href: 'a.tif', datetime: '2026-11-01T23:00:00Z', projection: 'EPSG:4326', bounds: [-130, 50, -120, 60], shape: [10, 10], transform: [1, 0, -130, 0, -1, 60], nodata: -9999, scale: 2, offset: 3 };
const to = { ...from, id: 'b', datetime: '2026-11-07T23:00:00Z', scale: 0.5, offset: -1 };

it('subtracts independently scaled physical values and intersects both masks', () => {
  const a = [10, 255, 0, 255, -9999, 255, 10, 0, 10, 255, NaN, 255, 10, 255];
  const b = [60, 255, 8, 255, 60, 255, 60, 255, 60, 0, 60, 255, Infinity, 255];
  expect(Array.from(subtractTiles(a, b, from, to))).toEqual([6, 255, 0, 255, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
  expect(Array.from(subtractTiles(b, a, to, from))).toEqual([-6, 255, 0, 255, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
  expect(Array.from(subtractTiles(a, a, from, from))).toEqual([0, 255, 0, 255, 0, 0, 0, 0, 0, 255, 0, 0, 0, 255]);
});

it('rejects shifted or incompatible grids but tolerates export rounding', () => {
  expect(() => assertAligned(from, { ...to, transform: [1, 0, -130 + 1e-13, 0, -1, 60] })).not.toThrow();
  expect(() => assertAligned(from, { ...to, transform: [1, 0, -129.5, 0, -1, 60] })).toThrow('different raster grids');
  expect(() => assertAligned(from, { ...to, shape: [10, 11] })).toThrow();
  expect(() => assertAligned(from, { ...to, projection: 'EPSG:3857' })).toThrow();
});

it('keys both dates and their order, and centres every variable colour scale on zero', () => {
  expect(differenceAsset(from, to).id).not.toBe(differenceAsset(to, from).id);
  expect(differenceAsset(from, to).id).not.toBe(to.id);
  expect(differenceAsset(from, to)).toMatchObject({ scale: 1, offset: 0, nodata: 'NaN' });
  expect(differenceVariable({ range: [-25, 10], id: 't' } as Variable).range).toEqual([-35, 35]);
});

it('exports the requested interval, both endpoints, and a signed difference with missing/error status', () => {
  const a = { time: from.datetime, value: 23 }, b = { time: to.datetime, value: 29 };
  expect(pointDifference(a, b)).toBe(6);
  expect(pointDifference(b, a)).toBe(-6);
  expect(pointDifference(a, a)).toBe(0);
  expect(pointDifference(a, { ...b, value: null })).toBeNull();
  expect(pointDifference(a, { ...b, error: 'HTTP failure' })).toBeNull();
  expect(differenceCSV(a, b, [-120, 50], 'mm')).toContain(`${a.time},${b.time},-120,50,23,29,6,"mm",valid`);
  expect(differenceCSV(a, { ...b, value: null }, [-120, 50], 'mm')).toContain('23,,,"mm",nodata');
  expect(differenceCSV(a, { ...b, value: null, error: 'HTTP failure' }, [-120, 50], 'mm')).toContain('23,,,"mm",error');
});
