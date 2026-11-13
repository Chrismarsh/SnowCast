import type { Asset, PointValue, Variable } from './types';

export interface MapAsset extends Asset { difference?: { from: Asset; to: Asset } }
export const differenceColors = ['#b35806', '#f1a340', '#f7f7f7', '#67a9cf', '#2166ac'];
export const temperatureDifferenceColors = ['#2166ac', '#67a9cf', '#f7f7f7', '#ef8a62', '#b2182b'];

export function differenceAsset(from: Asset, to: Asset): MapAsset {
  return { ...to, id: JSON.stringify(['difference', from.id, to.id]), scale: 1, offset: 0, nodata: 'NaN', difference: { from, to } };
}

export function differenceVariable(variable: Variable): Variable {
  const limit = variable.range[1] - variable.range[0];
  return { ...variable, id: `${variable.id}:difference`, title: `${variable.title} change`, palette: variable.palette === 'temperature' ? 'temperature-difference' : 'difference', range: [-limit, limit] };
}

/** Only subtract aligned cells; allow floating point noise from raster export. */
export function assertAligned(from: Asset, to: Asset) {
  const tolerance = Math.max(Math.abs(to.transform[0]), Math.abs(to.transform[4])) * 1e-6;
  if (from.projection !== to.projection || from.shape.some((v, i) => v !== to.shape[i]) ||
      from.transform.some((v, i) => Math.abs(v - to.transform[i]) > tolerance) ||
      from.transform[1] !== 0 || from.transform[3] !== 0 || to.transform[1] !== 0 || to.transform[3] !== 0) {
    throw new Error('These dates use different raster grids and cannot be subtracted. Choose dates on the same grid.');
  }
}

export function pointDifference(from?: PointValue, to?: PointValue): number | null {
  if (!from || !to || from.error || to.error || from.value == null || to.value == null) return null;
  const delta = to.value - from.value;
  return Number.isFinite(delta) ? delta : null;
}

export function differenceCSV(from: PointValue, to: PointValue, location: number[], unit: string): string {
  const value = pointDifference(from, to);
  const quote = (s: string) => '"' + s.replaceAll('"', '""') + '"';
  const status = from.error || to.error ? 'error' : value === null ? 'nodata' : 'valid';
  return 'from_datetime_utc,to_datetime_utc,longitude,latitude,from_value,to_value,to_minus_from,unit,status\r\n' +
    [from.sourceTime || from.time, to.sourceTime || to.time, ...location, from.value ?? '', to.value ?? '', value ?? '', quote(unit), status].join(',');
}
