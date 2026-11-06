import { expect, it } from 'vitest';
import { basemaps, initialBasemap } from './basemaps';

it('defaults to Esri topographic, remembers choices, and gives explicit links precedence', () => {
  expect(initialBasemap(null, null)).toBe('terrain');
  expect(initialBasemap(null, 'osm')).toBe('osm');
  expect(initialBasemap(null, 'satellite')).toBe('satellite');
  expect(initialBasemap('none', 'satellite')).toBe('none');
  expect(initialBasemap('osm', 'none')).toBe('osm');
  expect(initialBasemap('auto', 'none')).toBe('terrain');
  expect(initialBasemap(null, 'invalid')).toBe('terrain');
  expect(basemaps.none.url).toBeUndefined();
});
