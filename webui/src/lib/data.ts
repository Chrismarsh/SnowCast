import type { Asset, Catalogue, PointValue, Variable } from './types';
import type { EncodedExpression } from 'ol/expr/expression';
import { differenceColors, temperatureDifferenceColors } from './difference';

export const snowColors = ['#e4f8fc', '#9ae2ed', '#62b8ed', '#6981e5', '#7852de', '#6630bd'];
export const temperatureColors = ['#284ba3', '#70b6d5', '#e7f1ef', '#f9ca99', '#df815d', '#b8353d'];
export const paletteColors = (variable: Pick<Variable, 'palette'>) => variable.palette === 'temperature-difference' ? temperatureDifferenceColors : variable.palette === 'difference' ? differenceColors : variable.palette === 'temperature' ? temperatureColors : snowColors;

/** Single-band numeric GeoTIFF sources also supply validity in band 2. */
export function rasterColor(asset: Pick<Asset, 'nodata' | 'scale' | 'offset'>, variable: Pick<Variable, 'palette' | 'range'>, hideZeroSnow = false): EncodedExpression {
  const colors = paletteColors(variable);
  const raw: EncodedExpression = ['band', 1];
  const valid: EncodedExpression = ['all', ['>', ['band', 2], 0], ['==', raw, raw]];
  // Mask in raw units, before scaling or clamping to the display range.
  if (typeof asset.nodata === 'number' && Number.isFinite(asset.nodata)) valid.push(['!=', raw, asset.nodata]);
  const value: EncodedExpression = ['+', ['*', raw, asset.scale], asset.offset];
  // This is a display mask in physical units, not a change to valid data.
  if (hideZeroSnow && variable.palette === 'snow') valid.push(['!=', value, 0]);
  const ramp: EncodedExpression = ['interpolate', ['linear'], value];
  colors.forEach((color, i) => ramp.push(variable.range[0] + (variable.range[1] - variable.range[0]) * i / (colors.length - 1), color));
  return ['case', valid, ramp, [0, 0, 0, 0]];
}

// Kept outside Svelte: RasterSource serializes this function into a worker.
// It must not capture component state or compiler-generated helpers.
export function colorPixel(inputs: number[][] | ImageData[], data: any): number[] {
  const pixel = (inputs as number[][])[0];
  const raw = pixel[0];
  if (!Number.isFinite(raw) || raw === data.nodata || (pixel.length > 1 && !pixel[1])) return [0, 0, 0, 0];
  const value = raw * data.scale + data.offset;
  if (data.hideZero && value === 0) return [0, 0, 0, 0];
  const f = Math.max(0, Math.min(1, (value - data.min) / (data.max - data.min))) * (data.colors.length - 1);
  const i = Math.min(data.colors.length - 2, Math.floor(f));
  const t = f - i;
  return [0, 1, 2].map(c => data.colors[i][c] * (1 - t) + data.colors[i + 1][c] * t).concat(255);
}
export const dateLabel = (s: string) => new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' });
export const timeLabel = (s: string) => new Date(s).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'UTC' }) + ' UTC';
export const formatValue = (v: number | null | undefined, unit = 'mm') => v == null ? '—' : new Intl.NumberFormat('en-CA', { maximumFractionDigits: unit === 'm' ? 2 : 1 }).format(v);

export function pixelAt(lonlatInSourceCRS: number[], transform: number[], shape: number[]): [number, number] | null {
  const [a, b, c, d, e, f] = transform;
  const determinant = a * e - b * d;
  if (!Number.isFinite(determinant) || determinant === 0) throw new Error('Invalid raster transform');
  const [x, y] = [lonlatInSourceCRS[0] - c, lonlatInSourceCRS[1] - f];
  const col = Math.floor((e * x - b * y) / determinant);
  const row = Math.floor((-d * x + a * y) / determinant);
  return col >= 0 && row >= 0 && col < shape[1] && row < shape[0] ? [col, row] : null;
}

export function physicalValue(raw: number, nodata: number | 'NaN' | null, scale: number, offset: number): number | null {
  if (!Number.isFinite(raw) || (typeof nodata === 'number' && raw === nodata)) return null;
  const value = raw * scale + offset;
  return Number.isFinite(value) ? value : null;
}

export function normalizeCatalogue(raw: unknown, catalogueURL: string): Catalogue {
  const c = raw as Catalogue;
  if (c?.version !== 1 || !Array.isArray(c.variables) || !c.variables.length || !Array.isArray(c.bounds) || c.bounds.length !== 4 || !c.bounds.every(Number.isFinite)) throw new Error('Invalid or empty SnowCast catalogue');
  if (!Number.isFinite(Date.parse(c.latest_time)) || !Number.isFinite(Date.parse(c.generated_at))) throw new Error('Catalogue timestamps are invalid');
  if (!Number.isInteger(c.window_days) || c.window_days < 1 || c.window_days > 366) throw new Error('Invalid catalogue window');
  const ids = new Set<string>();
  for (const v of c.variables) {
    if (ids.has(v.id) || !v.id || !v.unit || !Array.isArray(v.assets) || !v.assets.length || !Array.isArray(v.range) || v.range.length !== 2 || !v.range.every(Number.isFinite) || v.range[0] >= v.range[1]) throw new Error('Invalid catalogue variable');
    ids.add(v.id);
    const times = new Set<string>();
    for (const a of v.assets) {
      if (!a.id || !Number.isFinite(Date.parse(a.datetime)) || !a.projection || a.transform?.length !== 6 || !a.transform.every(Number.isFinite) || a.shape?.length !== 2 || !a.shape.every(n => Number.isInteger(n) && n > 0) || a.bounds?.length !== 4 || !a.bounds.every(Number.isFinite) || !Number.isFinite(a.scale) || !Number.isFinite(a.offset)) throw new Error('Invalid raster metadata');
      if (times.has(a.datetime)) throw new Error('Duplicate valid time in catalogue');
      times.add(a.datetime);
      const url = new URL(a.href, catalogueURL);
      if (!['https:', 'http:'].includes(url.protocol)) throw new Error('Raster URLs must use HTTP(S)');
      a.href = url.href;
    }
    v.assets.sort((a, b) => Date.parse(a.datetime) - Date.parse(b.datetime));
  }
  return c;
}

export function seriesCSV(values: PointValue[], location: number[], unit: string, project?: string): string {
  const quote = (s: string) => '"' + s.replaceAll('"', '""') + '"';
  const attribution = project ? ',' + quote(project) : '';
  return ['datetime_utc,longitude,latitude,value,unit,status' + (project ? ',project' : ''), ...values.map(v => `${v.sourceTime || v.time},${location[0]},${location[1]},${v.value ?? ''},${quote(unit)},${quote(v.error ? 'error' : v.value === null ? 'nodata' : 'valid')}${attribution}`)].join('\r\n');
}
