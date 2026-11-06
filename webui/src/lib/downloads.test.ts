import { describe, expect, it } from 'vitest';
import { archiveURL, parseDownloadIndex, filterDownloads, fileSize, urlList } from './downloads';

const snapshot = (names: string[]) => ({ version: 1, source: archiveURL, indexed_at: '2026-11-06T18:00:00Z', files: names.map(name => ({ name, size: '379M' })) });
const names = ['swe-0.001x0.001_20260317T230000.tiff', 'swe-0.01x0.01_20260317T230000.tiff',
  'snowdepthavg-0.001x0.001_20260316T230000.tiff', 't-0.001x0.001_20260317T230000.tiff'];

describe('original TIFF download index', () => {
  it('uses original archive URLs and timestamps, preserving UTC dates and gaps', () => {
    const { files } = parseDownloadIndex(snapshot(names));
    expect(files).toHaveLength(4);
    expect(files[0].time).toBe('2026-03-17T23:00:00Z');
    expect(filterDownloads(files, 'swe', '0.001', '2026-03-17', '2026-03-17').map(f => f.href)).toEqual([archiveURL + names[0]]);
    expect(filterDownloads(files, '', '0.001', '2026-03-18', '')).toEqual([]);
    expect(filterDownloads(files, '', '0.01', '', '')).toHaveLength(1);
    expect(filterDownloads(files, '', '0.001', '2026-03-17', '2026-03-16')).toEqual([]);
  });
  it('ignores unsafe or malformed filenames and deduplicates entries', () => {
    const { files } = parseDownloadIndex(snapshot([...names, names[0], '../' + names[0], 'https://evil.example/' + names[0],
      names[0].replace('0317', '0230'), names[0].replace('0.001x0.001', '0.001x0.01')]));
    expect(files).toHaveLength(4);
    expect(() => parseDownloadIndex(snapshot([]))).toThrow('No TIFF files');
    expect(() => parseDownloadIndex({ ...snapshot(names), source: 'https://example.com/' })).toThrow('Invalid download index');
  });
  it('exports only matching download links and labels rounded file sizes', () => {
    const files = filterDownloads(parseDownloadIndex(snapshot(names)).files, '', '0.01', '', '');
    expect(urlList(files)).toBe(archiveURL + names[1] + '\n');
    expect(fileSize('379M')).toBe('≈ 379 MiB');
    expect(fileSize(null)).toBe('Size not listed');
  });
});
