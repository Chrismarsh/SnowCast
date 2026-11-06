import { expect, it } from 'vitest';
import { areaBounds, areas, areasWithin } from './areas';

it('offers the Rockies sites for the published western Canadian domain', () => {
  expect(areasWithin([-131.9952, 46.4615, -109.8028, 55.9981])).toEqual(areas);
  expect(areasWithin([-115.3, 50.8, -115.1, 51]).map(area => area.id)).toEqual(['marmot', 'fortress']);
});

it('does not send users to sites outside the catalogue bounds or an unknown domain', () => {
  expect(areasWithin([-106.8, 52, -106.5, 52.3])).toEqual([]);
  expect(areasWithin()).toEqual([]);
  expect(areasWithin([NaN, 50, -114, 53])).toEqual([]);
  expect(areasWithin([-115, 50])).toEqual([]);
});

it('fits a ground-distance viewing window around each site, accounting for latitude', () => {
  for (const area of areas) {
    const [west, south, east, north] = areaBounds(area);
    const [lon, lat] = area.center;
    expect((west + east) / 2).toBeCloseTo(lon, 6);
    expect((south + north) / 2).toBeCloseTo(lat, 6);
    expect((north - south) * 111.32).toBeCloseTo(area.radiusKm * 2, 6);
    expect((east - west) * 111.32 * Math.cos(lat * Math.PI / 180)).toBeCloseTo(area.radiusKm * 2, 6);
  }
});
