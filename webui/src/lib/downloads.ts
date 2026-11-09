export const archiveURL = 'https://hpfx.collab.science.gc.ca/~chm003/tiff/';
export const asciiArchiveURL = 'https://hpfx.collab.science.gc.ca/~chm003/asc/';
export const downloadVariables = [
  { id: 'swe', title: 'Snow water equivalent', short: 'SWE', unit: 'mm' },
  { id: 'snowdepthavg', title: 'Snow depth', short: 'Snow depth', unit: 'm' },
  { id: 't', title: 'Air temperature', short: 'Temperature', unit: '°C' },
] as const;
export type DownloadVariable = typeof downloadVariables[number]['id'];
export type Grid = '0.001' | '0.036';
export type DownloadFile = { name: string; href: string; variable: DownloadVariable; grid: Grid; format: 'GeoTIFF' | 'ASCII'; time: string; size: string | null };
export type DownloadIndex = { indexedAt: string; files: DownloadFile[] };

export function parseDownloadIndex(value: unknown): DownloadIndex {
  const index = value as { version?: number; source?: string; ascii_source?: string; indexed_at?: string; files?: { name: string; size?: string | null }[] };
  if (!index || index.version !== 1 || index.source !== archiveURL || !index.indexed_at || !Number.isFinite(Date.parse(index.indexed_at)) || !Array.isArray(index.files)) throw new Error('Invalid download index');
  if (index.ascii_source !== undefined && index.ascii_source !== asciiArchiveURL) throw new Error('Invalid ASCII archive');
  const files: DownloadFile[] = [];
  const seen = new Set<string>();
  for (const entry of index.files) {
    if (!entry || typeof entry.name !== 'string' || seen.has(entry.name)) continue;
    const tiff = /^(swe|snowdepthavg|t)-0\.001x0\.001_(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})\.tiff?$/.exec(entry.name);
    const ascii = index.ascii_source === asciiArchiveURL && /^(swe|snowdepthavg|t)_(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\.asc$/.exec(entry.name);
    const match = tiff || ascii;
    if (!match) continue;
    const [, variable, year, month, day, hour, minute, second] = match;
    const time = `${year}-${month}-${day}T${hour}:${minute}:${second}Z`;
    const date = new Date(time);
    if (!Number.isFinite(+date) || date.toISOString() !== time.replace('Z', '.000Z')) continue;
    seen.add(entry.name);
    files.push({ name: entry.name, href: (tiff ? archiveURL : asciiArchiveURL) + entry.name, variable: variable as DownloadVariable,
      grid: tiff ? '0.001' : '0.036', format: tiff ? 'GeoTIFF' : 'ASCII', time,
      size: typeof entry.size === 'string' && /^\d+(?:\.\d+)?[KMGT]?$/.test(entry.size) ? entry.size : null });
  }
  if (!files.length) throw new Error('No downloadable files are listed');
  files.sort((a, b) => b.time.localeCompare(a.time) || a.variable.localeCompare(b.variable) || a.grid.localeCompare(b.grid));
  return { indexedAt: index.indexed_at, files };
}

export function filterDownloads(files: DownloadFile[], variable: string, grid: Grid, from: string, to: string) {
  return files.filter(file => (!variable || file.variable === variable) && file.grid === grid && (!from || file.time.slice(0, 10) >= from) && (!to || file.time.slice(0, 10) <= to));
}

export function fileSize(size: string | null) {
  if (!size) return 'Size not listed';
  const suffix = size.slice(-1);
  const units: Record<string, string> = { K: 'KiB', M: 'MiB', G: 'GiB', T: 'TiB' };
  return units[suffix] ? `≈ ${size.slice(0, -1)} ${units[suffix]}` : `${size} B`;
}

const dateFormat = new Intl.DateTimeFormat('en-CA', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });
export function downloadDate(time: string) { return dateFormat.format(new Date(time)); }
export function urlList(files: DownloadFile[]) { return files.map(file => file.href).join('\n') + '\n'; }
