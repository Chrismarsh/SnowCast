import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Catalogue } from './types';
import { combinedCatalogue, focusedProject, framesForDay, loadProjects, parseSite, projectAsset, projectsAtPoint, type ProjectCatalogue } from './projects';
import { historyDates } from './history';
import { seriesCSV } from './data';
import { differenceCSV } from './difference';

const project = (id: string, bounds: number[], days: number[], range: [number, number] = [0, 400]): ProjectCatalogue => {
  const assets = days.map(day => ({ id: String(day), datetime: `2026-11-${day}T23:00:00Z`, href: `https://example.org/${id}/${day}.tif`,
    bounds, projection: 'EPSG:4326', transform: [.001, 0, bounds[0], 0, -.001, bounds[3]], shape: [32, 32], nodata: -9999, scale: 1, offset: 0 }));
  const catalogue: Catalogue = { version: 1, title: id, domain: { id, name: id }, generated_at: '2026-11-13T00:00:00Z',
    latest_time: assets.at(-1)!.datetime, window_days: 10, sample_data: true, bounds,
    variables: [{ id: 'swe', label: 'SWE', title: 'Snow water equivalent', unit: 'mm', range, palette: 'snow', assets }] };
  return { id, name: id, url: `https://example.org/${id}/catalog.json`, catalogue };
};
const west = () => project('west', [-125, 48, -110, 60], [10, 12]);
const tvc = () => project('tvc', [-135, 67, -130, 70], [10, 11], [0, 100]);
afterEach(() => vi.unstubAllGlobals());

describe('independent projects on a shared map', () => {
  it('unites daily slots without carrying stale assets across missing dates', () => {
    const projects = [west(), tvc()];
    const catalogue = combinedCatalogue(projects, 'SnowCast')!;
    const variable = catalogue.variables[0];
    expect(catalogue.bounds).toEqual([-135, 48, -110, 70]);
    expect(historyDates(variable, catalogue).filter(d => d.asset).map(d => d.time)).toEqual([
      '2026-11-10T00:00:00Z', '2026-11-11T00:00:00Z', '2026-11-12T00:00:00Z']);
    const day = framesForDay(projects, variable, '2026-11-12T00:00:00Z');
    expect(day.frames.map(f => f.project)).toEqual(['west']);
    expect(day.unavailable).toEqual(['tvc: no SWE for 2026-11-12']);
    expect(projectAsset(projects[1], 'swe', '2026-11-12T00:00:00Z')).toBeUndefined();
  });

  it('preserves actual output times within a shared UTC day', () => {
    const p = tvc(); p.catalogue.variables[0].assets.at(-1)!.datetime = '2026-11-11T12:00:00Z';
    expect(projectAsset(p, 'swe', '2026-11-11T00:00:00Z')!.datetime).toBe('2026-11-11T12:00:00Z');
    const value = { time: '2026-11-11T00:00:00Z', sourceTime: '2026-11-11T12:00:00Z', value: 3 };
    expect(seriesCSV([value], [0, 0], 'mm')).toContain('2026-11-11T12:00:00Z');
    expect(differenceCSV(value, value, [0, 0], 'mm')).not.toContain('2026-11-11T00:00:00Z');
  });

  it('subtracts dates only inside the same project and skips missing/incompatible pairs', () => {
    const projects = [west(), tvc()];
    let result = framesForDay(projects, west().catalogue.variables[0], '2026-11-12T00:00:00Z', '2026-11-10T00:00:00Z');
    expect(result.frames).toHaveLength(1);
    expect(result.frames[0].asset.difference?.from.href).toContain('/west/');
    expect(result.frames[0].asset.difference?.to.href).toContain('/west/');
    projects[0].catalogue.variables[0].assets[1].transform[2] += .01;
    result = framesForDay(projects, west().catalogue.variables[0], '2026-11-12T00:00:00Z', '2026-11-10T00:00:00Z');
    expect(result.frames).toHaveLength(0);
    expect(result.unavailable[0]).toContain('incompatible grids');
  });

  it('uses configured scales across dates and resolves focus/overlap without domain names', () => {
    const projects = [west(), tvc(), project('local', [-118, 50, -116, 52], [11], [0, 700])];
    expect(combinedCatalogue(projects, 'SnowCast')!.variables[0].range).toEqual([0, 700]);
    expect(combinedCatalogue(projects, 'SnowCast', { swe: [0, 900] })!.variables[0].range).toEqual([0, 900]);
    expect(focusedProject(projects, [-140, 40, -100, 75])).toBeUndefined();
    expect(focusedProject(projects, [-135, 67, -130, 70])?.id).toBe('tvc');
    expect(focusedProject(projects, [-117.9, 50.1, -116.1, 51.9])?.id).toBe('local');
    expect(projectsAtPoint(projects, [-117, 51]).map(p => p.id)).toEqual(['local', 'west']);
  });

  it('keeps healthy catalogues when a project is offline and namespaces identical asset IDs', async () => {
    const catalogues = [west(), tvc()];
    const site = parseSite({ version: 1, title: 'SnowCast', domains: [...catalogues.map(p => ({ id: p.id, name: p.name, catalogue: p.url })),
      { id: 'third', name: 'third', catalogue: './missing.json' }] }, 'https://example.org/site.json');
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const p = catalogues.find(p => p.url === url);
      return new Response(p ? JSON.stringify(p.catalogue) : '', { status: p ? 200 : 503 });
    }));
    const result = await loadProjects(site, new AbortController().signal);
    expect(result.projects.map(p => p.id)).toEqual(['west', 'tvc']);
    expect(result.warnings).toEqual(['third: Catalogue returned HTTP 503']);
    const ids = result.projects.map(p => p.catalogue.variables[0].assets[0].id);
    expect(ids[0]).not.toBe(ids[1]);
  });

  it('rejects identity/units mismatches without mixing another project into the map', async () => {
    const catalogues = [west(), tvc()];
    catalogues[1].catalogue.variables[0].unit = 'm';
    const site = parseSite({ version: 1, title: 'SnowCast', domains: catalogues.map(p => ({ id: p.id, name: p.name, catalogue: p.url })) }, 'https://example.org/site.json');
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(catalogues.find(p => p.url === url)!.catalogue))));
    let result = await loadProjects(site, new AbortController().signal);
    expect(result.projects.map(p => p.id)).toEqual(['west']);
    expect(result.warnings[0]).toContain('incompatible units');
    catalogues[1].catalogue.domain!.id = 'wrong';
    result = await loadProjects(site, new AbortController().signal);
    expect(result.warnings[0]).toContain('identity');
  });

  it('does not fetch unpublished projects or permit duplicate IDs and non-HTTP URLs', async () => {
    const domain = { id: 'new', name: 'New', catalogue: './data/new/catalog.json', available: false };
    const spec = { version: 1, title: 'Site', domains: [domain] };
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    expect((await loadProjects(parseSite(spec, 'https://example.org/site.json'), new AbortController().signal)).warnings).toEqual(['New: Not published yet']);
    expect(fetcher).not.toHaveBeenCalled();
    expect(() => parseSite({ ...spec, domains: [domain, domain] }, 'https://example.org/site.json')).toThrow('duplicate');
    expect(() => parseSite({ ...spec, domains: [{ ...domain, catalogue: 'javascript:bad()' }] }, 'https://example.org/site.json')).toThrow('HTTP');
  });
});
