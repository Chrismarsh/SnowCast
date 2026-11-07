/** GWFO navigation presets, not catchment boundaries or observation overlays.
 * Site membership: https://gwfo.ca/instrumented-sites.php (checked 2026-11-06).
 * Centres follow the linked site descriptions; radii are chosen viewing windows.
 */
export interface Area {
  id: string;
  name: string;
  region: string;
  center: [number, number]; // longitude, latitude (EPSG:4326)
  radiusKm: number;
  source: string;
}

export const areas: Area[] = [
  { id: 'marmot', name: 'Marmot Creek', region: 'Kananaskis', center: [-115.19, 50.96], radiusKm: 5, source: 'https://gwfo.ca/sites/crho/marmot-creek.php' },
  { id: 'fortress', name: 'Fortress Mountain', region: 'Kananaskis', center: [-115.22, 50.83], radiusKm: 5, source: 'https://gwfo.ca/sites/fortress.php' },
  { id: 'burstall', name: 'Burstall Creek', region: 'Kananaskis', center: [-115.41, 50.88], radiusKm: 5, source: 'https://gwfo.ca/sites/crho/burstall-creek.php' },
  { id: 'sibbald', name: 'Sibbald Wetlands', region: 'Kananaskis', center: [-114.869906, 51.058161], radiusKm: 4, source: 'https://www.nature.com/articles/s41598-026-50725-6' },
  { id: 'ohara', name: 'Lake O’Hara', region: 'Yoho', center: [-116.3375, 51.358333], radiusKm: 5, source: 'https://ccrnetwork.ca/science-programme/wecc-observatories/lake-ohara.php' },
  { id: 'bow-hut', name: 'Bow River Headwaters', region: 'Bow Hut', center: [-116.49, 51.64], radiusKm: 6, source: 'https://gwfo.ca/sites/crho/bow-river.php' },
  { id: 'helen', name: 'Helen Creek', region: 'Banff', center: [-116.41, 51.68], radiusKm: 5, source: 'https://gwfo.ca/sites/crho/helen-creek.php' },
  { id: 'peyto', name: 'Peyto Glacier', region: 'Wapta Icefield', center: [-116.55, 51.67], radiusKm: 7, source: 'https://gwfo.ca/sites/peyto.php' },
  { id: 'athabasca', name: 'Athabasca Glacier', region: 'Columbia Icefield', center: [-117.25, 52.19], radiusKm: 8, source: 'https://gwfo.ca/sites/crho/athabasca-glacier.php' },
];

/** Hide shortcuts outside the current catalogue extent.
 * An extent is only a bounding box: nodata inside it is still possible.
 */
export function areasWithin(bounds?: number[]): Area[] {
  if (!bounds || bounds.length !== 4 || !bounds.every(Number.isFinite)) return [];
  const [west, south, east, north] = bounds;
  return areas.filter(({ center: [lon, lat] }) => lon >= west && lon <= east && lat >= south && lat <= north);
}

export function areaBounds({ center: [lon, lat], radiusKm }: Area): number[] {
  const dy = radiusKm / 111.32;
  const dx = dy / Math.cos(lat * Math.PI / 180);
  return [lon - dx, lat - dy, lon + dx, lat + dy];
}
