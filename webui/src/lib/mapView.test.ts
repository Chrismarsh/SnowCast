import { describe, expect, it } from 'vitest';
import View from 'ol/View';
import { fromLonLat, toLonLat } from 'ol/proj';
import { MAP_MAX_ZOOM, mapViewParams, readMapView } from './mapView';

describe('shared map views', () => {
  it('round trips an OpenLayers centre and fractional zoom independently of the selected point', () => {
    const original = new View({ center: fromLonLat([-115.732419, 51.013275]), zoom: 11.3752, maxZoom: MAP_MAX_ZOOM });
    const [lon, lat] = toLonLat(original.getCenter()!);
    const params = new URLSearchParams('variable=swe&lon=-114.5&lat=50.5&station=TEST&mode=difference&from=2026-11-01&time=2026-11-05');
    mapViewParams(params, { lon, lat, zoom: original.getZoom()! });
    const state = readMapView(params)!;
    const restored = new View({ center: fromLonLat([state.lon, state.lat]), zoom: state.zoom, maxZoom: MAP_MAX_ZOOM });
    restored.getCenter()!.forEach((value, i) => expect(value).toBeCloseTo(original.getCenter()![i], 1));
    expect(restored.getZoom()).toBeCloseTo(original.getZoom()!, 4);
    expect(params.get('lon')).toBe('-114.5');
    expect(params.get('lat')).toBe('50.5');
    expect(params.get('station')).toBe('TEST');
    expect(params.get('mode')).toBe('difference');
    expect(params.get('from')).toBe('2026-11-01');
    expect(params.get('time')).toBe('2026-11-05');
  });

  it.each([
    '', 'lon=-115&lat=51', 'viewLon=-115&viewLat=51',
    'viewLon=&viewLat=51&zoom=10', 'viewLon=-115&viewLat= &zoom=10',
    'viewLon=-115&viewLat=51&zoom=NaN', 'viewLon=Infinity&viewLat=51&zoom=10',
    'viewLon=181&viewLat=51&zoom=10', 'viewLon=-115&viewLat=90&zoom=10',
    'viewLon=-115&viewLat=51&zoom=-1', 'viewLon=-115&viewLat=51&zoom=18',
  ])('falls back to the domain fit for absent or invalid views: %s', query => {
    expect(readMapView(new URLSearchParams(query))).toBeUndefined();
  });

  it.each([
    { lon: 0, lat: 0, zoom: 0 },
    { lon: -180, lat: -85.0511287798066, zoom: MAP_MAX_ZOOM },
    { lon: 180, lat: 85.0511287798066, zoom: MAP_MAX_ZOOM },
  ])('supports view-only links and rounded Mercator limits: %j', view => {
    const params = new URLSearchParams();
    mapViewParams(params, view);
    const restored = readMapView(params)!;
    expect(restored).toBeDefined();
    expect(restored.lon).toBeCloseTo(view.lon, 6);
    expect(restored.lat).toBeCloseTo(view.lat, 6);
    expect(restored.zoom).toBe(view.zoom);
    expect(params.has('lon')).toBe(false);
    expect(params.has('lat')).toBe(false);
  });
});
