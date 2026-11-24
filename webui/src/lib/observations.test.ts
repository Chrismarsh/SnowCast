import { describe, expect, it, vi } from 'vitest';
import { loadObservations, parseObservations } from './observations';
import { loadStation } from './stations';

const entry = { id: 'network', label: 'Snow network', description: 'Historical snow', release: '2025',
  renderer: 'snow-stations-v1', variables: { swe: 'mm' }, through: '2025-07-31',
  citation: 'Example', doi: 'https://example.org/source', licence: 'Example', licence_url: 'https://example.org/licence',
  index: 'observations/network/index-ab12.json' };
describe('runtime observation registry', () => {
  it('supports multiple datasets and resolves URLs below a deployed subdirectory', () => {
    const manifest = parseObservations({ version: 1, datasets: [entry, { ...entry, id: 'second', label: 'Second network', index: 'observations/second/index-cd34.json' }] }, 'https://example.org/v3-testing/observations.json');
    expect(manifest.datasets.map(d => d.label)).toEqual(['Snow network', 'Second network']);
    expect(manifest.datasets[0].index).toBe('https://example.org/v3-testing/observations/network/index-ab12.json');
    expect(parseObservations({ version: 1, datasets: [{ ...entry, renderer: 'future-raster' }] }).datasets).toEqual([]);
  });
  it('rejects duplicate identities and unsafe index paths', () => {
    for (const datasets of [[entry, entry], [{ ...entry, index: '../../private.json' }], [{ ...entry, index: 'https://other.example/index.json' }]]) {
      expect(() => parseObservations({ version: 1, datasets })).toThrow();
    }
  });
  it('handles an unpublished site and reports failures without hiding them', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response('', { status: 404 })).mockResolvedValueOnce(new Response('', { status: 503 }));
    vi.stubGlobal('fetch', fetcher);
    try {
      expect((await loadObservations(new AbortController().signal)).datasets).toEqual([]);
      await expect(loadObservations(new AbortController().signal)).rejects.toThrow('503');
      expect(fetcher.mock.calls[0][1].cache).toBe('no-cache');
    } finally { vi.unstubAllGlobals(); }
  });
  it('keeps history caches separate for identical station IDs across datasets', async () => {
    const bins = Array.from({ length: 24 }, (_, bin) => ({ bin, years: 0, first: null, last: null, q25: null, median: null, q75: null, samples: [] }));
    const station = { id: 'shared', name: 'Station', lon: -115, lat: 51, elevation: null, agency: 'Example', method: 'Manual', automated: false, first: '2025-01-01', last: '2025-01-01', counts: { swe: 1, depth: 0 }, href: 'stations/shared.json.gz' };
    const detail = (value: number) => ({ version: 1, id: 'shared', records: [['2025-01-01', value, null, '', '', '', '']], seasonal: { swe: bins, depth: bins } });
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(detail(10)))).mockResolvedValueOnce(new Response(JSON.stringify(detail(20))));
    vi.stubGlobal('fetch', fetcher);
    try {
      const signal = new AbortController().signal;
      expect((await loadStation(station, signal, 'https://example.org/observations/a/index-ab.json')).records[0][1]).toBe(10);
      expect((await loadStation(station, signal, 'https://example.org/observations/b/index-ab.json')).records[0][1]).toBe(20);
      expect(fetcher).toHaveBeenCalledTimes(2);
    } finally { vi.unstubAllGlobals(); }
  });
});
