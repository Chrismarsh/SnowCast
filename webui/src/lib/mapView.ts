export interface MapViewState { lon: number; lat: number; zoom: number }
export const MAP_MAX_ZOOM = 17;
// Web Mercator's latitude limit, rounded to the URL coordinate precision.
const MAX_LATITUDE = 85.051129;

/** View coordinates are separate from lon/lat, which identify a sampled point. */
export function readMapView(params: URLSearchParams): MapViewState | undefined {
  const values = ['viewLon', 'viewLat', 'zoom'].map(key => params.get(key));
  if (values.some(value => value === null || value.trim() === '')) return;
  const [lon, lat, zoom] = values.map(Number);
  if (![lon, lat, zoom].every(Number.isFinite) || Math.abs(lon) > 180 ||
      Math.abs(lat) > MAX_LATITUDE || zoom < 0 || zoom > MAP_MAX_ZOOM) return;
  return { lon, lat, zoom };
}

export function mapViewParams(params: URLSearchParams, view: MapViewState) {
  params.set('viewLon', view.lon.toFixed(6));
  params.set('viewLat', view.lat.toFixed(6));
  params.set('zoom', view.zoom.toFixed(4));
}
