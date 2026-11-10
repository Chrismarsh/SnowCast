export const basemaps = {
  osm: {
    label: 'OpenStreetMap',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attributions: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
  terrain: {
    label: 'Esri topographic',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
    attributions: 'Tiles © Esri — Esri, HERE, Garmin, USGS, NRCan',
    maxZoom: 17,
  },
  satellite: {
    label: 'Esri satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attributions: 'Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community',
    maxZoom: 17,
  },
  none: { label: 'None — data only', url: undefined, attributions: '', maxZoom: 19 },
} as const;

export type BasemapId = keyof typeof basemaps;
export const DEFAULT_BASEMAP: BasemapId = 'terrain';
export const basemapIds = Object.keys(basemaps) as BasemapId[];
export const BASEMAP_STORAGE_KEY = 'snowcast-basemap';
export function isBasemap(value: string | null | undefined): value is BasemapId {
  return !!value && Object.hasOwn(basemaps, value);
}
export function initialBasemap(requested: string | null, saved: string | null): BasemapId {
  if (isBasemap(requested)) return requested;
  if (requested === 'auto') return DEFAULT_BASEMAP;
  return isBasemap(saved) ? saved : DEFAULT_BASEMAP;
}
