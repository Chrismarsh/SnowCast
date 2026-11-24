import type { Asset, Catalogue, Variable } from './types';
import { normalizeCatalogue } from './data';
import { assertAligned, differenceAsset, differenceVariable, type MapAsset } from './difference';

export interface ProjectCatalogue { id: string; name: string; url: string; catalogue: Catalogue }
export interface SiteManifest {
  version: number; title: string;
  domains: { id: string; name: string; catalogue: string; available?: boolean }[];
  overview_ranges?: Record<string, [number, number]>;
}
export interface ModelFrame { project: string; name: string; asset: MapAsset; variable: Variable }
export const dayKey = (time: string) => time.slice(0, 10);
export const contains = (bounds: number[], point: number[]) => point[0] >= bounds[0] && point[0] <= bounds[2] && point[1] >= bounds[1] && point[1] <= bounds[3];

export function parseSite(raw: unknown, url: string): SiteManifest {
  const site = raw as SiteManifest;
  if (site?.version !== 1 || typeof site.title !== 'string' || !site.title.trim() || !Array.isArray(site.domains)) throw new Error('Invalid SnowCast site manifest');
  const ids = new Set<string>();
  for (const entry of site.domains) {
    if (!entry || typeof entry.id !== 'string' || !/^[a-z][a-z0-9_-]{0,63}$/.test(entry.id) || ids.has(entry.id) || typeof entry.name !== 'string' || !entry.name.trim() || typeof entry.catalogue !== 'string' ||
        (entry.available !== undefined && typeof entry.available !== 'boolean')) throw new Error('Invalid or duplicate site project');
    ids.add(entry.id);
    const target = new URL(entry.catalogue, url);
    if (!['https:', 'http:'].includes(target.protocol)) throw new Error('Project catalogues must use HTTP(S)');
    entry.catalogue = target.href;
  }
  if (site.overview_ranges !== undefined && (!site.overview_ranges || typeof site.overview_ranges !== 'object' || Array.isArray(site.overview_ranges))) throw new Error('Invalid site overview ranges');
  for (const span of Object.values(site.overview_ranges || {})) {
    if (!Array.isArray(span) || span.length !== 2 || !span.every(Number.isFinite) || span[0] >= span[1]) throw new Error('Invalid site overview ranges');
  }
  return site;
}

export async function loadProjects(site: SiteManifest, signal: AbortSignal): Promise<{ projects: ProjectCatalogue[]; warnings: string[] }> {
  const results = await Promise.allSettled(site.domains.map(async entry => {
    if (entry.available === false) throw new Error('Not published yet');
    const response = await fetch(entry.catalogue, { cache: 'no-cache', signal: AbortSignal.any([signal, AbortSignal.timeout(20000)]) });
    if (!response.ok) throw new Error(`Catalogue returned HTTP ${response.status}`);
    const catalogue = normalizeCatalogue(await response.json(), entry.catalogue);
    if (catalogue.domain?.id !== entry.id) throw new Error('Catalogue project identity does not match the website');
    // Identical asset IDs from independent publishers must never share a cache entry.
    for (const variable of catalogue.variables) for (const asset of variable.assets) asset.id = JSON.stringify([entry.id, asset.id]);
    return { id: entry.id, name: entry.name, url: entry.catalogue, catalogue };
  }));
  const projects: ProjectCatalogue[] = [], warnings: string[] = [];
  results.forEach((result, index) => {
    if (result.status === 'rejected') {
      warnings.push(`${site.domains[index].name}: ${result.reason instanceof Error ? result.reason.message : 'Unavailable'}`);
      return;
    }
    const incompatible = result.value.catalogue.variables.find(v => projects.some(p => p.catalogue.variables.some(
      previous => previous.id === v.id && (previous.unit !== v.unit || previous.palette !== v.palette))));
    if (incompatible) warnings.push(`${result.value.name}: incompatible units or palette for ${incompatible.id}`);
    else projects.push(result.value);
  });
  return { projects, warnings };
}

export function projectAsset(project: ProjectCatalogue, variable: string, time?: string): Asset | undefined {
  return time ? project.catalogue.variables.find(v => v.id === variable)?.assets.filter(a => dayKey(a.datetime) === dayKey(time)).at(-1) : undefined;
}

/** A timeline only: these representative assets are never read or rendered. */
export function combinedCatalogue(projects: ProjectCatalogue[], title: string, ranges: SiteManifest['overview_ranges'] = {}): Catalogue | null {
  if (!projects.length) return null;
  const catalogues = projects.map(p => p.catalogue);
  const variables = new Map<string, Variable>();
  for (const catalogue of catalogues) for (const v of catalogue.variables) {
    const previous = variables.get(v.id);
    if (previous && (previous.unit !== v.unit || previous.palette !== v.palette)) throw new Error(`Projects use incompatible units or palettes for ${v.id}`);
    variables.set(v.id, previous ? { ...previous, assets: [...previous.assets, ...v.assets],
      range: [Math.min(previous.range[0], v.range[0]), Math.max(previous.range[1], v.range[1])] } : { ...v, assets: [...v.assets], range: [...v.range] });
  }
  for (const v of variables.values()) {
    if (ranges?.[v.id]) v.range = ranges[v.id];
    const days = new Map<string, Asset>();
    for (const a of v.assets) {
      const day = dayKey(a.datetime);
      days.set(day, { ...a, id: JSON.stringify(['site', v.id, day]), datetime: `${day}T00:00:00Z` });
    }
    v.assets = [...days.values()].sort((a, b) => a.datetime.localeCompare(b.datetime));
  }
  return { ...catalogues[0], title, domain: undefined,
    latest_time: catalogues.map(c => c.latest_time).sort().at(-1)!,
    generated_at: catalogues.map(c => c.generated_at).sort().at(-1)!,
    window_days: Math.max(...catalogues.map(c => c.window_days)), sample_data: catalogues.every(c => c.sample_data),
    bounds: [Math.min(...catalogues.map(c => c.bounds[0])), Math.min(...catalogues.map(c => c.bounds[1])),
             Math.max(...catalogues.map(c => c.bounds[2])), Math.max(...catalogues.map(c => c.bounds[3]))],
    variables: [...variables.values()] };
}

export function framesForDay(projects: ProjectCatalogue[], variable: Variable | undefined, to?: string, from?: string) {
  const frames: ModelFrame[] = [], unavailable: string[] = [];
  if (!variable || !to) return { frames, unavailable };
  for (const project of projects) {
    const target = projectAsset(project, variable.id, to), previous = projectAsset(project, variable.id, from);
    if (!target || (from && !previous)) { unavailable.push(`${project.name}: no ${variable.label} for ${from ? 'both selected dates' : dayKey(to)}`); continue; }
    try {
      if (previous) assertAligned(previous, target);
      frames.push({ project: project.id, name: project.name, asset: previous ? differenceAsset(previous, target) : target,
        variable: previous ? differenceVariable(variable) : variable });
    } catch { unavailable.push(`${project.name}: selected dates use incompatible grids`); }
  }
  return { frames, unavailable };
}

export function projectsAtPoint(projects: ProjectCatalogue[], point: number[]) {
  return [...projects].reverse().filter(p => contains(p.catalogue.bounds, point));
}

/** Last configured project wins overlaps. A shared scale is used in overview. */
export function focusedProject(projects: ProjectCatalogue[], extent?: number[]): ProjectCatalogue | undefined {
  if (!extent) return;
  const area = (b: number[]) => Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]);
  const visible = projects.filter(p => area([Math.max(extent[0], p.catalogue.bounds[0]), Math.max(extent[1], p.catalogue.bounds[1]),
    Math.min(extent[2], p.catalogue.bounds[2]), Math.min(extent[3], p.catalogue.bounds[3])]) > 0);
  if (visible.length === 1) return visible[0];
  const center = [(extent[0] + extent[2]) / 2, (extent[1] + extent[3]) / 2];
  return [...visible].reverse().find(p => contains(p.catalogue.bounds, center) && area([
    Math.max(extent[0], p.catalogue.bounds[0]), Math.max(extent[1], p.catalogue.bounds[1]),
    Math.min(extent[2], p.catalogue.bounds[2]), Math.min(extent[3], p.catalogue.bounds[3])]) >= area(extent) * .8);
}
