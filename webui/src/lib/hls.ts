/** NASA HLS v2, mirrored and rendered by Microsoft Planetary Computer. */
export const HLS_STAC = 'https://planetarycomputer.microsoft.com/api/stac/v1';
export const HLS_TILES = 'https://planetarycomputer.microsoft.com/api/data/v1';
export const HLS_MIN_ZOOM = 7;
export const HLS_MAX_ZOOM = 12;
export const HLS_TILE_SIZE = 256;
export const HLS_COLLECTIONS = ['hls2-s30', 'hls2-l30'] as const;
export type HlsCollection = typeof HLS_COLLECTIONS[number];
export type HlsView = 'true-color' | 'snow';
export type HlsSettings = { enabled: boolean; mode: 'latest' | 'date'; date: string; days: number; view: HlsView; opacity: number };
export type HlsScene = { id: string; collection: HlsCollection; datetime: string; platform: string; bounds: number[] };
export type HlsWindow = { start: string; end: string };
export type HlsStatus = { pending: number; loaded: number; empty: number; failed: number; first?: string; last?: string; error?: string };
export type HlsPick = { state: 'ready'; scene: HlsScene } | { state: 'empty' | 'loading' | 'error' | 'zoom' };

export function utcDay(now = new Date()): string { return now.toISOString().slice(0, 10); }
export function validDay(day: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(day) && Number.isFinite(Date.parse(day)) && new Date(day).toISOString().slice(0, 10) === day;
}
export function initialHls(params = new URLSearchParams()): HlsSettings {
  const today = utcDay();
  const date = params.get('sat-date') || today;
  const days = Number(params.get('sat-days') || 7);
  const opacity = Number(params.get('sat-opacity') || 0.85);
  return {
    enabled: params.get('satellite') === '1', mode: params.get('sat-mode') === 'date' ? 'date' : 'latest',
    date: validDay(date) && date <= today && date >= '2020-01-01' ? date : today,
    days: [3, 7, 14, 30].includes(days) ? days : 7,
    view: params.get('sat-view') === 'snow' ? 'snow' : 'true-color',
    opacity: Number.isFinite(opacity) && opacity >= 0 && opacity <= 1 ? opacity : 0.85,
  };
}
export function hlsWindow(settings: HlsSettings, today = utcDay()): HlsWindow {
  const end = settings.mode === 'latest' ? today : settings.date;
  if (!validDay(end) || end > today || end < '2020-01-01') throw new Error('Choose a satellite date between 2020-01-01 and today.');
  const days = settings.mode === 'latest' ? settings.days : 1;
  if (![1, 3, 7, 14, 30].includes(days)) throw new Error('Invalid satellite lookback window.');
  const start = new Date(Date.parse(end) - (days - 1) * 86400000).toISOString().slice(0, 10);
  return { start: start < '2020-01-01' ? '2020-01-01' : start, end };
}
export function hlsParams(params: URLSearchParams, settings: HlsSettings) {
  for (const key of ['satellite', 'sat-mode', 'sat-date', 'sat-days', 'sat-view', 'sat-opacity']) params.delete(key);
  if (settings.enabled) {
    params.set('satellite', '1'); params.set('sat-mode', settings.mode); params.set('sat-view', settings.view);
    params.set('sat-opacity', String(settings.opacity));
    if (settings.mode === 'date') params.set('sat-date', settings.date);
    else params.set('sat-days', String(settings.days));
  }
}
export function sceneLabel(scene: HlsScene): string {
  return scene.platform.replace(/^sentinel-2([abc])$/i, (_, unit) => `Sentinel-2${unit.toUpperCase()}`)
    .replace(/^landsat-?([89])$/i, 'Landsat $1');
}
export function tileBounds(z: number, x: number, y: number): number[] {
  const n = 2 ** z;
  const latitude = (row: number) => Math.atan(Math.sinh(Math.PI * (1 - 2 * row / n))) * 180 / Math.PI;
  return [x / n * 360 - 180, latitude(y + 1), (x + 1) / n * 360 - 180, latitude(y)];
}
export function searchURL(bounds: number[], window: HlsWindow): string {
  const params = new URLSearchParams({ collections: HLS_COLLECTIONS.join(','), bbox: bounds.join(','),
    datetime: `${window.start}T00:00:00Z/${window.end}T23:59:59.999Z`, sortby: '-datetime', limit: '100',
    fields: 'id,collection,bbox,properties.datetime,properties.platform' });
  return `${HLS_STAC}/search?${params}`;
}
export function parseScenes(features: unknown, window: HlsWindow): HlsScene[] {
  if (!Array.isArray(features)) throw new Error('Satellite catalogue returned an invalid scene list.');
  return features.map((f): HlsScene => {
    if (!f || typeof f.id !== 'string' || !HLS_COLLECTIONS.includes(f.collection) ||
        typeof f.properties?.datetime !== 'string' || !Number.isFinite(Date.parse(f.properties.datetime)) ||
        !Array.isArray(f.bbox) || f.bbox.length !== 4 || !f.bbox.every(Number.isFinite)) {
      throw new Error('Satellite catalogue returned invalid scene metadata.');
    }
    const datetime = new Date(f.properties.datetime).toISOString();
    if (datetime.slice(0, 10) < window.start || datetime.slice(0, 10) > window.end) throw new Error('Satellite scene is outside the requested dates.');
    return { id: f.id, collection: f.collection, datetime, bounds: f.bbox,
      platform: typeof f.properties.platform === 'string' ? f.properties.platform : f.collection === 'hls2-s30' ? 'Sentinel-2' : 'Landsat 8/9' };
  });
}
export function sortScenes(scenes: HlsScene[]): HlsScene[] {
  return [...new Map(scenes.map(s => [`${s.collection}/${s.id}`, s])).values()]
    .sort((a, b) => b.datetime.localeCompare(a.datetime) || a.id.localeCompare(b.id));
}
export function sceneTileURL(scene: HlsScene, view: HlsView, z: number, x: number, y: number): string {
  // SWIR1/NIR/red: snow and ice appear cyan. Use each sensor's equivalent bands.
  const bands = view === 'true-color' ? ['B04', 'B03', 'B02']
    : scene.collection === 'hls2-s30' ? ['B11', 'B8A', 'B04'] : ['B06', 'B05', 'B04'];
  // Fmask bits 1,2,3 are cloud/adjacent cloud/shadow; preserve snow (bit 4)
  // and water (bit 5). Modulo avoids numexpr integer bitwise incompatibilities.
  // Explicit alpha also excludes QA fill=255 and reflectance fill=-9999.
  const valid = ['((Fmask % 16) < 2)', ...bands.map(b => `(${b} != -9999)`)].join(' & ');
  const params = new URLSearchParams({ collection: scene.collection, item: scene.id, asset_as_band: 'true',
    expression: `${bands.join(';')};where(${valid},255,0)`, return_mask: 'false',
    resampling: 'nearest', reproject: 'nearest', color_formula: 'Gamma RGB 2.2' });
  for (const range of ['0,10000', '0,10000', '0,10000', '0,255']) params.append('rescale', range);
  return `${HLS_TILES}/item/tiles/WebMercatorQuad/${z}/${x}/${y}.png?${params}`;
}
/** Fill only still-empty pixels; callers supply scenes newest first, across both sensors. */
export function compositeScene(output: Uint8ClampedArray, provenance: Uint16Array, pixels: Uint8ClampedArray, sceneIndex: number): number {
  if (pixels.length !== output.length || output.length !== provenance.length * 4) throw new Error('Unexpected satellite tile dimensions.');
  let added = 0;
  for (let i = 0; i < provenance.length; i++) {
    const p = i * 4;
    if (provenance[i] || pixels[p + 3] !== 255) continue;
    output[p] = pixels[p]; output[p + 1] = pixels[p + 1]; output[p + 2] = pixels[p + 2]; output[p + 3] = 255;
    provenance[i] = sceneIndex + 1; added++;
  }
  return added;
}
