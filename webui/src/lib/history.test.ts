import { describe, expect, it } from 'vitest';
import { historyDates, historySelection } from './history';
import type { Asset, Catalogue, Variable } from './types';

const asset = (time: string) => ({ datetime: time, id: time }) as Asset;
const catalogue = { latest_time: '2026-11-09T23:00:00Z', window_days: 10 } as Catalogue;
const variable = { assets: [asset('2026-10-18T23:00:00Z'), asset('2026-10-25T23:00:00Z'),
  asset('2026-11-01T12:00:00Z'), asset('2026-11-01T23:00:00Z'), asset('2026-11-09T23:00:00Z')] } as Variable;

describe('daily and weekly history', () => {
  it('defaults to ten daily slots with genuine missing days', () => {
    const dates = historyDates(variable, catalogue);
    expect(dates).toHaveLength(10);
    expect(dates[0].time.slice(0, 10)).toBe('2026-10-31');
    expect(dates[0].asset).toBeUndefined();
    expect(dates[1].asset?.datetime).toBe('2026-11-01T23:00:00Z');
  });
  it('adds sparse older snapshots without filling the intervening days', () => {
    const dates = historyDates(variable, catalogue, true);
    expect(dates).toHaveLength(12);
    expect(dates.slice(0, 2).map(d => d.time)).toEqual(variable.assets.slice(0, 2).map(a => a.datetime));
    expect(dates.filter(d => d.asset)).toHaveLength(4);
  });
  it('preserves selected dates when archive slots change their indices', () => {
    const recent = historyDates(variable, catalogue);
    const all = historyDates(variable, catalogue, true);
    expect(historySelection(all, recent[9].time, recent[1].time)).toEqual({ to: 11, from: 3 });
    expect(historySelection(recent, all[11].time, all[3].time)).toEqual({ to: 9, from: 1 });
  });
  it('falls back to available dates when changing to temperature without an archive', () => {
    const temperature = { assets: [asset('2026-11-09T23:00:00Z')] } as Variable;
    const dates = historyDates(temperature, catalogue, true);
    expect(dates).toHaveLength(10);
    expect(historySelection(dates, '2026-10-18T23:00:00Z', '2026-10-25T23:00:00Z')).toEqual({ to: 9, from: 9 });
  });
});
