import { describe, expect, it } from 'vitest';
import { archiveURL, asciiArchiveURL, parseDownloadIndex, filterDownloads, fileSize, urlList } from './downloads';

const snapshot = (names: string[]) => ({ version: 1, source: archiveURL, ascii_source: asciiArchiveURL, indexed_at: '2026-11-06T18:00:00Z', files: names.map(name => ({ name, size: '379M' })) });
const names = ['swe-0.001x0.001_20260317T230000.tiff', 'swe-0.01x0.01_20260317T230000.tiff',
  'snowdepthavg-0.001x0.001_20260316T230000.tiff', 't-0.001x0.001_20260317T230000.tiff'];

describe('daily download index', () => {
  it('uses original archive URLs and timestamps, preserving UTC dates and gaps', () => {
    const { files } = parseDownloadIndex(snapshot(names));
    expect(files).toHaveLength(3);
    expect(files[0].time).toBe('2026-03-17T23:00:00Z');
    expect(filterDownloads(files, 'swe', '0.001', '2026-03-17', '2026-03-17').map(f => f.href)).toEqual([archiveURL + names[0]]);
    expect(filterDownloads(files, '', '0.001', '2026-03-18', '')).toEqual([]);
    expect(files.some(f => f.name === names[1])).toBe(false);
    expect(filterDownloads(files, '', '0.001', '2026-03-17', '2026-03-16')).toEqual([]);
  });
  it('ignores unsafe or malformed filenames and deduplicates entries', () => {
    const { files } = parseDownloadIndex(snapshot([...names, names[0], '../' + names[0], 'https://evil.example/' + names[0],
      names[0].replace('0317', '0230'), names[0].replace('0.001x0.001', '0.001x0.01')]));
    expect(files).toHaveLength(3);
    expect(() => parseDownloadIndex(snapshot([]))).toThrow('No downloadable files');
    expect(() => parseDownloadIndex({ ...snapshot(names), source: 'https://example.com/' })).toThrow('Invalid download index');
  });
  it('exports only matching download links and labels rounded file sizes', () => {
    const files = filterDownloads(parseDownloadIndex(snapshot(names)).files, 'swe', '0.001', '', '');
    expect(urlList(files)).toBe(archiveURL + names[0] + '\n');
    expect(fileSize('379M')).toBe('≈ 379 MiB');
    expect(fileSize(null)).toBe('Size not listed');
  });
  it('filters AEP ASCII by variable and UTC date with links to the ASCII archive', () => {
    const ascii = ['swe_20261108230000.asc', 'swe_20261109230000.asc', 't_20261109230000.asc'];
    const { files } = parseDownloadIndex(snapshot([...names, ...ascii, ascii[0], '../' + ascii[0],
      'swe_20260230230000.asc', 'swe_20261109230000.prj', 'swe-0.036x0.036_20261109T230000.tiff']));
    expect(files).toHaveLength(6);
    expect(files[0].time).toBe('2026-11-09T23:00:00Z');
    const selected = filterDownloads(files, 'swe', '0.036', '2026-11-09', '2026-11-09');
    expect(selected).toMatchObject([{ grid: '0.036', format: 'ASCII', href: asciiArchiveURL + ascii[1] }]);
    expect(urlList(selected)).toBe(asciiArchiveURL + ascii[1] + '\n');
    expect(filterDownloads(files, 'snowdepthavg', '0.036', '', '')).toEqual([]);
    expect(filterDownloads(files, '', '0.001', '', '').every(f => f.format === 'GeoTIFF')).toBe(true);
  });
  it('accepts old TIFF-only indexes without resurfacing coarse files or trusting arbitrary ASCII sources', () => {
    const old = { ...snapshot(names), ascii_source: undefined };
    expect(parseDownloadIndex(old).files).toHaveLength(3);
    expect(() => parseDownloadIndex({ ...old, ascii_source: 'https://example.com/' })).toThrow('Invalid ASCII archive');
  });
});

const projectIndex = (id = 'tvc') => ({ version: 2, project: { id, name: 'Trail Valley Creek' }, indexed_at: '2026-11-13T18:00:00Z', sources: [{
  id: 'hpfx', name: 'HPFX', url: 'https://archive.example/tvc/', files: [{ name: 'swe-100x100_20261113T230000.tiff',
    path: 'tiff/swe-100x100_20261113T230000.tiff', variable: 'swe', format: 'GeoTIFF', time: '2026-11-13T23:00:00Z',
    crs: 'EPSG:32608', resolution: [100, 100], bytes: 2048, sidecars: ['tiff/swe-100x100_20261113T230000.tiff.msk'] }],
}] });

it('reads project identity, actual projected grids and companion files from successful archives', () => {
  const parsed = parseDownloadIndex(projectIndex(), 'tvc');
  expect(parsed.sources).toEqual([{ id: 'hpfx', name: 'HPFX', url: 'https://archive.example/tvc/' }]);
  expect(parsed.files[0]).toMatchObject({ grid: 'GeoTIFF:EPSG:32608:100x100', gridLabel: '100 × 100 (EPSG:32608 units)',
    href: 'https://archive.example/tvc/tiff/swe-100x100_20261113T230000.tiff', source: 'hpfx', size: '2048' });
  expect(parsed.files[0].sidecars?.[0].href).toContain('.tiff.msk');
  expect(urlList(parsed.files).trim().split('\n')).toEqual([parsed.files[0].href, parsed.files[0].sidecars![0].href]);
  expect(() => parseDownloadIndex(projectIndex(), 'western-cordillera')).toThrow('Invalid project');
});

it('keeps identical dates separate across mirrors and accepts a project awaiting archival', () => {
  const index = projectIndex();
  index.sources.push({ ...index.sources[0], id: 's3', name: 'Object store', url: 'https://s3.example/tvc/' });
  expect(parseDownloadIndex(index).files).toHaveLength(2);
  expect(parseDownloadIndex({ ...index, sources: [], indexed_at: null }).files).toEqual([]);
});

it.each(['../outside.tiff', 'tiff/../../outside.tiff', 'https://evil.example/file', 'tiff/%2e%2e/file'])('rejects unsafe archive paths %s', path => {
  const index = projectIndex(); index.sources[0].files[0].path = path;
  expect(() => parseDownloadIndex(index)).toThrow('Invalid archived file');
});

it('rejects executable links and impossible archive dates', () => {
  const index = projectIndex(); index.sources[0].url = 'javascript:alert(1)';
  expect(() => parseDownloadIndex(index)).toThrow('Invalid archive URL');
  index.sources[0].url = 'https://archive.example/';
  index.sources[0].files[0].time = '2026-02-30T23:00:00Z';
  expect(() => parseDownloadIndex(index)).toThrow('Invalid archived file');
});
