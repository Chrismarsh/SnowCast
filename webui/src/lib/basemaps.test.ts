import { expect, it } from 'vitest';
import { basemaps, initialBasemap } from './basemaps';

it('defaults to OSM, remembers choices, and gives explicit links precedence', () => {
  expect(initialBasemap(null, null)).toBe('osm');
  expect(initialBasemap(null, 'satellite')).toBe('satellite');
  expect(initialBasemap('none', 'satellite')).toBe('none');
  expect(initialBasemap('osm', 'none')).toBe('osm');
  expect(initialBasemap('auto', 'none')).toBe('osm');
  expect(initialBasemap(null, 'invalid')).toBe('osm');
  expect(basemaps.none.url).toBeUndefined();
});
