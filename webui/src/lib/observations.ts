export interface ObservationDataset {
  id: string; label: string; description: string; renderer: string; release: string;
  variables: Partial<Record<'swe' | 'depth', string>>;
  through: string; citation: string; doi: string; licence: string; licence_url: string;
  methods_url?: string; index: string;
}
export interface ObservationRegistry { version: number; datasets: ObservationDataset[] }
export const OBSERVATIONS_URL = new URL('./observations.json', typeof document === 'undefined' ? 'http://localhost/' : document.baseURI).href;

export function parseObservations(value: unknown, url = OBSERVATIONS_URL): ObservationRegistry {
  const raw = value as ObservationRegistry;
  if (raw?.version !== 1 || !Array.isArray(raw.datasets)) throw new Error('Invalid observation registry');
  const seen = new Set<string>();
  const datasets = raw.datasets.map(entry => {
    if (!/^[a-z][a-z0-9_-]{0,63}$/.test(entry.id) || seen.has(entry.id) ||
        typeof entry.label !== 'string' || !entry.label || typeof entry.description !== 'string' ||
        typeof entry.release !== 'string' || typeof entry.through !== 'string' ||
        typeof entry.renderer !== 'string' || !entry.variables ||
        !/^observations\/[a-z][a-z0-9_-]*\/index-[a-f0-9]+\.json$/.test(entry.index)) {
      throw new Error('Invalid observation dataset');
    }
    seen.add(entry.id);
    return { ...entry, index: new URL(entry.index, url).href };
  });
  // Other renderers can be added without breaking older deployed clients.
  return { version: 1, datasets: datasets.filter(d => d.renderer === 'snow-stations-v1') };
}

export async function loadObservations(signal: AbortSignal): Promise<ObservationRegistry> {
  const response = await fetch(OBSERVATIONS_URL, { cache: 'no-cache', signal });
  // A fresh standalone UI has no published observations yet.
  if (response.status === 404) return { version: 1, datasets: [] };
  if (!response.ok) throw new Error(`Observation registry returned HTTP ${response.status}`);
  return parseObservations(await response.json());
}
