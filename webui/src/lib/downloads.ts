export const archiveURL = 'https://hpfx.collab.science.gc.ca/~chm003/tiff/';
export const asciiArchiveURL = 'https://hpfx.collab.science.gc.ca/~chm003/asc/';
export const downloadVariables = [
  { id: 'swe', title: 'Snow water equivalent', short: 'SWE', unit: 'mm' },
  { id: 'snowdepthavg', title: 'Snow depth', short: 'Snow depth', unit: 'm' },
  { id: 't', title: 'Air temperature', short: 'Temperature', unit: '°C' },
] as const;
export type DownloadVariable = typeof downloadVariables[number]['id'];
export type Grid = string;
export type DownloadFile = { name: string; href: string; variable: DownloadVariable; grid: Grid; format: 'GeoTIFF' | 'ASCII'; time: string; size: string | null; source: string; gridLabel: string; sidecars?: { name: string; href: string }[] };
export type DownloadIndex = { indexedAt: string; files: DownloadFile[]; sources: { id: string; name: string; url: string }[] };
export type DownloadProject = { id: string; name: string; index: string; legacy?: boolean };

export function parseDownloadIndex(value: unknown, project?: string): DownloadIndex {
  if ((value as { version?: number })?.version === 2) return parseProjectDownloads(value, project);
  if (project) throw new Error('Expected a project download index');
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
      grid: tiff ? '0.001' : '0.036', gridLabel: tiff ? '0.001° × 0.001°' : '0.036° × 0.036°', source: 'hpfx', format: tiff ? 'GeoTIFF' : 'ASCII', time,
      size: typeof entry.size === 'string' && /^\d+(?:\.\d+)?[KMGT]?$/.test(entry.size) ? entry.size : null });
  }
  if (!files.length) throw new Error('No downloadable files are listed');
  files.sort((a, b) => b.time.localeCompare(a.time) || a.variable.localeCompare(b.variable) || a.grid.localeCompare(b.grid));
  return { indexedAt: index.indexed_at, files, sources: [{ id: 'hpfx', name: 'HPFX', url: archiveURL }] };
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


function httpURL(value: string) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('Invalid archive URL');
  return url;
}

function parseProjectDownloads(value: unknown, project?: string): DownloadIndex {
  const index = value as { project: { id: string }; indexed_at: string | null; sources: {
    id: string; name: string; url: string; files: { name: string; path: string; variable: string; time: string;
      format: 'GeoTIFF' | 'ASCII'; resolution: number[]; crs: string; bytes: number; sidecars?: string[] }[] }[] };
  if (!index.project || (project && index.project.id !== project) || !Array.isArray(index.sources) ||
      (index.sources.length > 0 && !Number.isFinite(Date.parse(index.indexed_at || '')))) throw new Error('Invalid project download index');
  const files: DownloadFile[] = [], sources: DownloadIndex['sources'] = [], ids = new Set<string>();
  for (const source of index.sources) {
    if (!/^[a-z][a-z0-9_-]{0,63}$/.test(source.id) || ids.has(source.id) || typeof source.name !== 'string' || !source.name || !Array.isArray(source.files)) throw new Error('Invalid archive source');
    ids.add(source.id);
    const base = httpURL(source.url.endsWith('/') ? source.url : source.url + '/');
    sources.push({ id: source.id, name: source.name, url: base.href });
    const seen = new Set<string>();
    for (const entry of source.files) {
      const path = /^(tiff|asc)\/([a-zA-Z0-9_.+-]+)$/.exec(entry.path);
      if (!path || path[2] !== entry.name || !downloadVariables.some(v => v.id === entry.variable) ||
          !['GeoTIFF', 'ASCII'].includes(entry.format) || (entry.format === 'GeoTIFF' ? path[1] !== 'tiff' : path[1] !== 'asc') ||
          !Number.isFinite(Date.parse(entry.time)) || new Date(entry.time).toISOString() !== entry.time.replace('Z', '.000Z') ||
          !Array.isArray(entry.resolution) || entry.resolution.length !== 2 || !entry.resolution.every(n => Number.isFinite(n) && n > 0) ||
          typeof entry.crs !== 'string' || !/^EPSG:\d+$/.test(entry.crs) || !Number.isSafeInteger(entry.bytes) || entry.bytes < 0 || seen.has(entry.path)) throw new Error('Invalid archived file');
      seen.add(entry.path);
      const degrees = entry.crs === 'EPSG:4326';
      const gridLabel = entry.resolution.map(n => `${n}${degrees ? '°' : ''}`).join(' × ') + (degrees ? '' : ` (${entry.crs} units)`);
      const sidecars = (entry.sidecars || []).map(path => {
        if (!/^(tiff|asc)\/[a-zA-Z0-9_.+-]+$/.test(path)) throw new Error('Invalid archive sidecar');
        return { name: path.split('/').pop()!, href: new URL(path, base).href };
      });
      files.push({ name: entry.name, href: new URL(entry.path, base).href, variable: entry.variable as DownloadVariable,
        time: entry.time, format: entry.format, grid: `${entry.format}:${entry.crs}:${entry.resolution.join('x')}`,
        gridLabel, source: source.id, size: String(entry.bytes), sidecars });
    }
  }
  files.sort((a, b) => b.time.localeCompare(a.time) || a.variable.localeCompare(b.variable));
  return { indexedAt: index.indexed_at || '', files, sources };
}

/** A unified site never falls back to another project's legacy download list. */
export async function downloadProjects(siteURL: string, signal: AbortSignal): Promise<DownloadProject[]> {
  const response = await fetch(siteURL, { cache: 'no-cache', signal });
  if (response.status === 404) return [{ id: 'western-cordillera', name: 'Western Cordillera', legacy: true,
    index: new URL('./download-index.json', siteURL).href }];
  if (!response.ok) throw new Error(`Project list returned HTTP ${response.status}`);
  const site = await response.json();
  if (site?.version !== 1 || !Array.isArray(site.domains)) throw new Error('Invalid project list');
  const ids = new Set<string>();
  return site.domains.map((entry: { id: string; name: string; catalogue: string }) => {
    if (!/^[a-z][a-z0-9_-]{0,63}$/.test(entry.id) || ids.has(entry.id) || !entry.name || typeof entry.catalogue !== 'string') throw new Error('Invalid download project');
    ids.add(entry.id);
    const catalogue = httpURL(new URL(entry.catalogue, siteURL).href);
    return { id: entry.id, name: entry.name, index: new URL('./downloads.json', catalogue).href };
  });
}
