import type { PointValue } from './types';

export interface SnowStation {
  id: string; name: string; lon: number; lat: number; elevation: number | null;
  agency: string; method: string; automated: boolean; first: string; last: string;
  counts: { swe: number; depth: number }; href: string;
}
export interface StationIndex {
  version: number; dataset: { name: string; version: string; doi: string; through: string; citation: string; licence: string; licence_url: string };
  stations: SnowStation[]; minimum_years: number; summary: string;
}
// Date, mm SWE, m depth, SWE/depth agency flags, SWE/depth CanSWE QC flags.
export type Observation = [string, number | null, number | null, string, string, string, string];
export interface SeasonalBin { bin: number; years: number; first: number | null; last: number | null; q25: number | null; median: number | null; q75: number | null; samples: [number, number][] }
export interface StationData { version: number; id: string; records: Observation[]; seasonal: { swe: SeasonalBin[]; depth: SeasonalBin[] } }
export type SnowVariable = 'swe' | 'depth';
export const STATION_INDEX_URL = new URL('./observations/canswe/index.json', typeof document === 'undefined' ? 'http://localhost/' : document.baseURI).href;
export const agencyFlags: Record<string, string> = { A: 'Sampling problems', B: 'Outside nominal sampling period', C: 'Sampling problems and outside nominal period', E: 'Estimated', G: 'Measurement more than 1 km from station', M: 'Missing', P: 'Patches', R: 'Revised', T: 'Trace', Y: 'Precise sampling date unavailable' };
export const qcFlags: Record<string, string> = { H: 'Snow depth outside QC range', M: 'Previously masked', V: 'Outlier', W: 'SWE outside QC range', D: 'Density failed QC' };
const cache = new Map<string, StationData>();
const isoDate = /^\d{4}-\d{2}-\d{2}$/;
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const nullable = (v: unknown) => v === null || finite(v);

export function snowVariable(id?: string): SnowVariable | null {
  return id === 'swe' ? 'swe' : id === 'snowdepthavg' || id === 'snowdepth' ? 'depth' : null;
}
export function inBounds(station: SnowStation, bounds: number[]): boolean {
  return station.lon >= bounds[0] && station.lon <= bounds[2] && station.lat >= bounds[1] && station.lat <= bounds[3];
}
export function snowYear(value: string): number { return Number(value.slice(0, 4)) + (Number(value.slice(5, 7)) >= 8 ? 1 : 0); }
export function halfMonth(value: string): number { return ((Number(value.slice(5, 7)) + 4) % 12) * 2 + (Number(value.slice(8, 10)) > 15 ? 1 : 0); }
// Common non-leap Aug–Jul axis; Feb 29 shares the Feb 28 seasonal position.
export function seasonDay(value: string): number {
  const month = Number(value.slice(5, 7)) - 1, day = Math.min(Number(value.slice(8, 10)), month === 1 ? 28 : 31);
  return (Date.UTC(month >= 7 ? 2000 : 2001, month, day) - Date.UTC(2000, 7, 1)) / 86400000;
}
export function binExtent(bin: number): [number, number] {
  const month = (7 + Math.floor(bin / 2)) % 12, year = month >= 7 ? 2000 : 2001;
  const start = Date.UTC(year, month, bin % 2 ? 16 : 1);
  const end = bin % 2 ? Date.UTC(year, month + 1, 1) : Date.UTC(year, month, 16);
  const origin = Date.UTC(2000, 7, 1);
  return [(start - origin) / 86400000, (end - origin) / 86400000];
}
export function binLabel(bin: number): string {
  const [start, end] = binExtent(bin);
  const format = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });
  const origin = Date.UTC(2000, 7, 1);
  return `${format.format(origin + start * 86400000)}–${format.format(origin + (end - 1) * 86400000)}`;
}
export function observationValue(row: Observation, variable: SnowVariable): number | null { return row[variable === 'swe' ? 1 : 2]; }
export function flagsLabel(row: Observation, variable: SnowVariable): string {
  const agency = row[variable === 'swe' ? 3 : 4], qc = row[variable === 'swe' ? 5 : 6];
  return [agency && (agencyFlags[agency] || agency), qc && `QC: ${qcFlags[qc] || qc}`].filter(Boolean).join('; ');
}
export function matchedModel(row: Observation, values: PointValue[], variable: SnowVariable): PointValue | undefined {
  // Dates without a known sampling day cannot support a same-date comparison.
  if (row[variable === 'swe' ? 3 : 4] === 'Y') return undefined;
  return values.find(v => v.time.slice(0, 10) === row[0] && !v.error && v.value !== null);
}
export function observationComparison(records: Observation[], model: PointValue[], year: number) {
  // The observation-year picker never restricts model coverage. Charts align
  // seasons by month/day; only matchedModel may make calendar-date matches.
  const modelFinite = model.filter(v => v.value !== null && !v.error);
  const modelYears = [...new Set(modelFinite.map(v => snowYear(v.time)))].sort((a, b) => a - b);
  return {
    observations: records.filter(r => snowYear(r[0]) === year),
    model, // Retain missing/failed samples so chart paths break at gaps.
    modelFinite,
    modelSeasons: modelYears.map(y => `${y - 1}–${y}`).join(', '),
    differentSeasons: modelYears.some(y => y !== year),
    modelDates: modelFinite.map(v => v.time.slice(0, 10)).sort(),
  };
}
export function parseIndex(value: unknown): StationIndex {
  const data = value as StationIndex;
  if (data?.version !== 1 || !Array.isArray(data.stations) || !data.dataset?.doi || data.minimum_years < 1) throw new Error('Invalid CanSWE index');
  const ids = new Set<string>();
  for (const s of data.stations) {
    if (!s.id || ids.has(s.id) || typeof s.name !== 'string' || !finite(s.lon) || !finite(s.lat) || Math.abs(s.lon) > 180 || Math.abs(s.lat) > 90 || !nullable(s.elevation) || !s.counts || !isoDate.test(s.first) || !isoDate.test(s.last) || !/^stations\/[\w.-]+\.json(?:\.gz)?$/.test(s.href)) throw new Error('Invalid CanSWE station');
    ids.add(s.id);
  }
  return data;
}
export function parseStation(value: unknown, id: string): StationData {
  const data = value as StationData;
  if (data?.version !== 1 || data.id !== id || !Array.isArray(data.records)) throw new Error('Invalid CanSWE history');
  let previous = '';
  for (const row of data.records) {
    if (row.length !== 7 || !isoDate.test(row[0]) || row[0] <= previous || !nullable(row[1]) || !nullable(row[2]) || row.slice(3).some(v => typeof v !== 'string')) throw new Error('Invalid CanSWE observation');
    previous = row[0];
  }
  for (const variable of ['swe', 'depth'] as const) {
    if (data.seasonal?.[variable]?.length !== 24 || data.seasonal[variable].some((b, i) => b.bin !== i || !Number.isInteger(b.years) || ![b.q25, b.median, b.q75].every(nullable) || !Array.isArray(b.samples))) throw new Error('Invalid CanSWE seasonal summary');
  }
  return data;
}
export async function loadStation(station: SnowStation, signal: AbortSignal): Promise<StationData> {
  const url = new URL(station.href, STATION_INDEX_URL).href;
  if (cache.has(url)) return cache.get(url)!;
  const response = await fetch(url, { signal: AbortSignal.any([signal, AbortSignal.timeout(20000)]) });
  if (!response.ok) throw new Error(`CanSWE history returned HTTP ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  // Works with ordinary .gz files AND servers adding Content-Encoding: gzip
  // (in which case fetch already decompressed the body).
  const text = bytes[0] === 0x1f && bytes[1] === 0x8b
    ? await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text()
    : new TextDecoder().decode(bytes);
  signal.throwIfAborted();
  const data = parseStation(JSON.parse(text), station.id);
  cache.set(url, data);
  if (cache.size > 8) cache.delete(cache.keys().next().value!);
  return data;
}
export function observationCSV(station: SnowStation, data: StationData): string {
  const cell = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  return ['station_id,date,swe_mm,snow_depth_m,agency_flag_swe,agency_flag_depth,qc_flag_swe,qc_flag_depth', ...data.records.map(r => [station.id, ...r].map(cell).join(','))].join('\r\n');
}
