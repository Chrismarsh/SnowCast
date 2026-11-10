import type { Asset, Catalogue, Variable } from './types';

export interface HistoryDate { time: string; asset?: Asset }

/** Older weekly snapshots are sparse; only the recent daily window has gap slots. */
export function historyDates(variable: Variable | undefined, catalogue: Catalogue | null, archive = false): HistoryDate[] {
  if (!variable?.assets.length) return [];
  const days = catalogue?.window_days || 10;
  const latest = new Date(catalogue?.latest_time || variable.assets.at(-1)!.datetime);
  const start = new Date(latest);
  start.setUTCHours(0, 0, 0, 0);
  start.setUTCDate(start.getUTCDate() - days + 1);
  const byDay = new Map<string, Asset>();
  for (const asset of [...variable.assets].sort((a, b) => a.datetime.localeCompare(b.datetime))) {
    byDay.set(asset.datetime.slice(0, 10), asset);
  }
  const older = archive ? [...byDay.values()].filter(a => Date.parse(a.datetime) < start.getTime())
    .map(asset => ({ time: asset.datetime, asset })) : [];
  const recent = Array.from({ length: days }, (_, index) => {
    const day = new Date(start); day.setUTCDate(day.getUTCDate() + index);
    const asset = byDay.get(day.toISOString().slice(0, 10));
    return { time: asset?.datetime || day.toISOString(), asset };
  });
  return [...older, ...recent];
}

/** Index positions change when history or variable changes; preserve actual dates. */
export function historySelection(dates: HistoryDate[], toTime?: string, fromTime?: string) {
  const foundTo = dates.findIndex(d => d.asset?.datetime === toTime);
  const to = foundTo >= 0 ? foundTo : dates.reduce((last, d, i) => d.asset ? i : last, -1);
  const foundFrom = dates.findIndex(d => d.asset?.datetime === fromTime);
  const earlier = dates.reduce((last, d, i) => i < to && d.asset ? i : last, -1);
  const from = foundFrom >= 0 ? foundFrom : earlier >= 0 ? earlier : dates.findIndex(d => d.asset);
  return { to, from };
}
