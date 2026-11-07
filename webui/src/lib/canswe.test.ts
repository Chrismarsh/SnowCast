import { describe, expect, it, vi } from 'vitest';
import { gzipSync } from 'node:zlib';
import { binExtent, flagsLabel, halfMonth, inBounds, loadStation, matchedModel, observationComparison, observationCSV, parseIndex, parseStation, seasonDay, snowVariable, snowYear, type Observation, type SnowStation, type StationData } from './canswe';

const station: SnowStation = { id: 'ALE-test', name: 'Test', lon: -115, lat: 51, elevation: 2000, agency: 'Alberta', method: 'Manual', automated: false, first: '2000-04-01', last: '2020-04-01', counts: { swe: 1, depth: 0 }, href: 'stations/ALE-test-123.json.gz' };
const record: Observation = ['2020-04-01', 0, null, 'T', '', '', ''];
const bins = Array.from({ length: 24 }, (_, bin) => ({ bin, years: 0, first: null, last: null, q25: null, median: null, q75: null, samples: [] }));
const data: StationData = { version: 1, id: station.id, records: [record], seasonal: { swe: bins, depth: bins } };

describe('station seasonal dates', () => {
  it('uses Aug–Jul snow seasons and stable leap-year alignment', () => {
    expect(snowYear('2025-08-01')).toBe(2026);
    expect(snowYear('2025-07-31')).toBe(2025);
    expect(seasonDay('2024-02-29')).toBe(seasonDay('2025-02-28'));
    expect(seasonDay('2025-08-01')).toBe(0);
    expect(seasonDay('2025-07-31')).toBe(364);
    expect(seasonDay('2026-01-01') - seasonDay('2025-12-31')).toBe(1);
    expect(halfMonth('2020-04-15')).toBe(16);
    expect(halfMonth('2020-04-16')).toBe(17);
    expect(binExtent(0)).toEqual([0, 15]);
    expect(binExtent(23)[1]).toBe(365);
  });
  it('requires the same date and never pairs an uncertain observation date', () => {
    const model = [{ time: '2020-04-01T23:00:00Z', value: 12 }, { time: '2026-04-01T23:00:00Z', value: 99 }];
    expect(matchedModel(record, model, 'swe')?.value).toBe(12);
    expect(matchedModel(['2021-04-01', 5, null, '', '', '', ''], model, 'swe')).toBeUndefined();
    expect(matchedModel(['2020-04-01', 5, null, 'Y', '', '', ''], model, 'swe')).toBeUndefined();
  });
});
describe('observation comparison with current SnowCast output', () => {
  const records: Observation[] = [
    ['2023-11-04', 5, .05, '', '', '', ''],
    ['2024-11-04', 10, .1, '', '', '', ''],
  ];
  const model = [{ time: '2026-11-04T23:00:00Z', value: 0 }, { time: '2026-11-05T23:00:00Z', value: 45 }];
  it('keeps current model values when selecting either historical observation season', () => {
    for (const year of [2024, 2025]) {
      const view = observationComparison(records, model, year);
      expect(view.observations).toEqual([records[year - 2024]]);
      expect(view.model).toEqual(model);
      expect(view.modelFinite).toEqual(model);
      expect(view.modelSeasons).toBe('2026–2027');
      expect(view.differentSeasons).toBe(true);
      expect(view.modelDates).toEqual(['2026-11-04', '2026-11-05']);
      expect(matchedModel(view.observations[0], view.model, 'swe')).toBeUndefined();
    }
  });
  it('retains gaps in chart paths while omitting failed/missing samples from points and coverage labels', () => {
    const samples = [{ time: '2025-07-31T23:00:00Z', value: null }, { time: '2025-08-01T23:00:00Z', value: 99, error: 'Read failed' }, ...model];
    const view = observationComparison(records, samples, 2025);
    expect(view.model).toEqual(samples);
    expect(view.modelFinite).toEqual(model);
    expect(view.modelSeasons).toBe('2026–2027');
    expect(observationComparison(records, [], 2025).modelFinite).toEqual([]);
    expect(observationComparison(records, [], 2025).modelSeasons).toBe('');
  });
  it('preserves exact-date matches and zero while excluding uncertain dates', () => {
    const sameDate: Observation = ['2026-11-04', 5, null, '', '', '', ''];
    const view = observationComparison([sameDate], model, 2027);
    expect(view.differentSeasons).toBe(false);
    expect(matchedModel(sameDate, view.model, 'swe')?.value).toBe(0);
    expect(matchedModel(['2026-11-04', 5, null, 'Y', '', '', ''], view.model, 'swe')).toBeUndefined();
    expect(observationComparison([], model, 2027).modelFinite).toEqual(model);
  });
});
it('preserves zero, missing depth and source flags in downloads', () => {
  expect(observationCSV(station, data)).toContain('"ALE-test","2020-04-01","0","","T","","",""');
  expect(flagsLabel(record, 'swe')).toBe('Trace');
  expect(flagsLabel(record, 'depth')).toBe('');
  expect(snowVariable('snowdepthavg')).toBe('depth');
  expect(snowVariable('t')).toBeNull();
});
it('filters domain stations without substituting nearby sites', () => {
  expect(inBounds(station, [-116, 50, -114, 52])).toBe(true);
  expect(inBounds(station, [-114, 50, -110, 52])).toBe(false);
});
it('rejects mismatched, duplicated or invalid station data', () => {
  expect(parseStation(data, station.id)).toBe(data);
  expect(() => parseStation(data, 'other')).toThrow();
  expect(() => parseStation({ ...data, records: [record, record] }, station.id)).toThrow();
  expect(() => parseStation({ ...data, records: [['2020-04-01', NaN, null, '', '', '', '']] }, station.id)).toThrow();
  const index = { version: 1, minimum_years: 10, dataset: { doi: 'https://doi.org/example' }, stations: [station] };
  expect(parseIndex(index).stations).toHaveLength(1);
  expect(() => parseIndex({ ...index, stations: [station, station] })).toThrow();
  expect(() => parseIndex({ ...index, stations: [{ ...station, href: '../../private.json' }] })).toThrow();
});
it('reads gzip histories or HTTP-decoded bodies, caches successes, and permits retry after failure', async () => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
  try {
    fetcher.mockResolvedValueOnce(new Response(gzipSync(JSON.stringify(data))));
    const signal = new AbortController().signal;
    expect((await loadStation(station, signal)).records).toEqual([record]);
    await loadStation(station, signal);
    expect(fetcher).toHaveBeenCalledTimes(1);
    const other = { ...station, id: 'other', href: 'stations/other.json.gz' };
    fetcher.mockResolvedValueOnce(new Response('Unavailable', { status: 503 }));
    await expect(loadStation(other, signal)).rejects.toThrow('503');
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify({ ...data, id: 'other' })));
    expect((await loadStation(other, signal)).id).toBe('other');
  } finally { vi.unstubAllGlobals(); }
});
