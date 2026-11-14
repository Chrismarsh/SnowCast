<script lang="ts">
  import { onMount } from 'svelte';
  import OLMap from 'ol/Map';
  import View from 'ol/View';
  import TileLayer from 'ol/layer/Tile';
  import XYZ from 'ol/source/XYZ';
  import VectorLayer from 'ol/layer/Vector';
  import VectorSource from 'ol/source/Vector';
  import Cluster from 'ol/source/Cluster';
  import Feature from 'ol/Feature';
  import Point from 'ol/geom/Point';
  import { Circle, Fill, Stroke, Style, Text } from 'ol/style';
  import { fromLonLat, toLonLat, transformExtent } from 'ol/proj';
  import { defaults } from 'ol/control';
  import type { SnowStation } from '../lib/stations';
  import { basemaps, DEFAULT_BASEMAP, type BasemapId } from '../lib/basemaps';
  import { displayPixelRatio, TileProgress } from '../lib/mapPerformance';
  import { MAP_MAX_ZOOM, type MapViewState } from '../lib/mapView';
  import { initialRenderer, isRendererPreference, RendererSelection, RENDERER_STORAGE_KEY, type RendererPreference } from '../lib/renderer';
  import { HlsSource } from '../lib/hlsSource';
  import { HLS_MIN_ZOOM, hlsWindow, initialHls, type HlsSettings, type HlsStatus, type HlsPick } from '../lib/hls';
  import { ModelLayers } from '../lib/modelLayers';
  import type { ModelFrame } from '../lib/projects';
  import 'ol/ol.css';
  export let frames: ModelFrame[] = [];
  export let selectionId = '';
  export let opacity = 0.7;
  export let hideZeroSnow = false;
  export let point: number[] | null = null;
  export let initialView: MapViewState | undefined = undefined;
  export let onviewchange: (view: MapViewState, extent: number[]) => void = () => {};
  export let bounds = [-132, 46.4, -109.8, 56];
  export let basemap: BasemapId = DEFAULT_BASEMAP;
  export let onpick: (point: number[]) => void;
  export let onready: (id: string, errors: string[]) => void;
  export let onerror: (error: string) => void;
  export let onslow: (id: string) => void = () => {};
  export let stations: SnowStation[] = [];
  export let stationsVisible = true;
  export let onstation: (station: SnowStation) => void = () => {};
  export let onstationcluster: (stations: SnowStation[]) => void = () => {};
  export let satellite: HlsSettings = initialHls();
  export let satelliteRevision = 0;
  export let onsatellitestatus: (status: HlsStatus, zoomedOut: boolean) => void = () => {};
  export let onsatellitepick: (pick: HlsPick | null) => void = () => {};
  let satelliteLayer: TileLayer<HlsSource>;
  let satelliteKey = '';
  let satelliteStatusFrame = 0;
  let target: HTMLDivElement;
  let map: OLMap;
  let mounted = false;
  let marker: VectorSource;
  let stationSource: VectorSource;
  let stationLayer: VectorLayer<Cluster>;
  let base: TileLayer<XYZ>;
  let rendering: RendererSelection;
  let models: ModelLayers;
  let fitted = false;
  let baseProgress = new TileProgress();
  let baseMode = '';
  const options = new URLSearchParams(window.location.search);
  const lowDetail = options.get('detail') === 'low';

  export function viewState(): MapViewState | undefined {
    const view = map?.getView(), center = view?.getCenter(), zoom = view?.getZoom();
    if (!view || !center || zoom === undefined) return;
    const [lon, lat] = toLonLat(center, view.getProjection());
    if ([lon, lat, zoom].every(Number.isFinite)) return { lon, lat, zoom };
  }

  export function fit(duration = 400, targetBounds = bounds) {
    if (!map) return;
    const view = map.getView();
    view.cancelAnimations();
    // Keep a user's chosen area if they navigate before the first COG is ready.
    fitted = true;
    view.fit(transformExtent(targetBounds, 'EPSG:4326', view.getProjection()), {
      padding: targetBounds === bounds ? [65, 30, 165, 30] : [110, 40, 180, 40],
      duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : duration,
    });
  }
  export function zoom(delta: number) { if (map) map.getView().animate({ zoom: (map.getView().getZoom() || 8) + delta, duration: 200 }); }
  export function focusStation(station: SnowStation) {
    if (!map) return;
    fitted = true;
    map.getView().animate({ center: fromLonLat([station.lon, station.lat]), zoom: Math.max(map.getView().getZoom() || 8, 11), duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 250 });
  }
  export function retry() { models?.retry(); }

  export function diagnostics() {
    return JSON.stringify({ ...models?.diagnostics(), detail: lowDetail ? 'low' : 'automatic', hideZeroSnow,
      viewport: map?.getSize(), devicePixelRatio: window.devicePixelRatio, mapPixelRatio: map?.getPixelRatio(),
      projection: map?.getView().getProjection().getCode(), basemap, basemapTiles: baseProgress.snapshot(),
      satellite: satellite.enabled ? { mode: satellite.mode, view: satellite.view, ...hlsWindow(satellite),
        ...satelliteLayer?.getSource()?.status(map.getView().calculateExtent(map.getSize()), map.getView().getResolution() || 1) } : { enabled: false },
    }, null, 2);
  }

  function setBasemap(mode: BasemapId) {
    if (baseMode === mode) return;
    baseMode = mode;
    const old = base.getSource();
    baseProgress = new TileProgress();
    const counter = baseProgress;
    const definition = basemaps[mode];
    base.setVisible(mode !== 'none');
    if (!definition.url) {
      base.setSource(null); old?.dispose(); return;
    }
    const source = new XYZ({ ...definition, crossOrigin: 'anonymous', transition: 0 });
    source.on('tileloadstart', e => counter.start(e.tile));
    source.on('tileloadend', e => counter.end(e.tile));
    source.on('tileloaderror', e => counter.end(e.tile, true));
    base.setSource(source);
    old?.dispose();
  }

  onMount(() => {
    let savedRenderer: string | null = null;
    try { savedRenderer = localStorage.getItem(RENDERER_STORAGE_KEY); } catch { /* Session-only mode. */ }
    const requestedRenderer = options.get('renderer');
    const preference = initialRenderer(requestedRenderer, savedRenderer);
    if (isRendererPreference(requestedRenderer)) rememberRenderer(requestedRenderer);
    const probe = preference === 'canvas' ? null : document.createElement('canvas').getContext('webgl2');
    rendering = new RendererSelection(preference, !!probe, rememberRenderer);
    probe?.getExtension('WEBGL_lose_context')?.loseContext();
    base = new TileLayer({ preload: 0 });
    satelliteLayer = new TileLayer({ zIndex: 20, preload: 0, cacheSize: 64, visible: false, minZoom: HLS_MIN_ZOOM - 0.001 });
    marker = new VectorSource();
    stationSource = new VectorSource();
    const stationStyles = new globalThis.Map<string, Style>();
    stationLayer = new VectorLayer({ source: new Cluster({ distance: 32, source: stationSource }), zIndex: 40,
      style: feature => {
        const members = feature.get('features') as Feature[];
        const count = members.length, automated = count === 1 && (members[0].get('station') as SnowStation).automated;
        const key = `${count}:${automated}`;
        if (!stationStyles.has(key)) stationStyles.set(key, new Style({
          image: new Circle({ radius: count > 1 ? 12 : 5, fill: new Fill({ color: count > 1 || automated ? '#9b6b36' : '#fffdf7' }), stroke: new Stroke({ color: count > 1 ? '#fffdf7' : '#9b6b36', width: 1.7 }) }),
          text: count > 1 ? new Text({ text: String(count), fill: new Fill({ color: 'white' }), font: '600 10px sans-serif' }) : undefined,
        }));
        return stationStyles.get(key)!;
      },
    });
    map = new OLMap({
      target,
      pixelRatio: displayPixelRatio(window.devicePixelRatio, [target.clientWidth, target.clientHeight], lowDetail),
      controls: defaults({ zoom: false, rotate: false, attributionOptions: { collapsible: false } }),
      layers: [base, satelliteLayer, stationLayer, new VectorLayer({
        source: marker, zIndex: 50,
        style: new Style({ image: new Circle({ radius: 7, fill: new Fill({ color: '#08777a' }), stroke: new Stroke({ color: 'white', width: 3 }) }) }),
      })],
      // Restore a shared view before loading tiles; otherwise await domain bounds.
      view: new View({ projection: 'EPSG:3857', maxZoom: MAP_MAX_ZOOM,
        ...(initialView ? { center: fromLonLat([initialView.lon, initialView.lat]), zoom: initialView.zoom } : {}),
      }),
    });
    models = new ModelLayers(map, rendering, {
      ready: (id, errors) => onready(id, errors), error: message => onerror(message), slow: id => onslow(id),
    });
    fitted = !!initialView;
    map.on('moveend', () => {
      queueSatelliteStatus();
      const view = viewState();
      if (view) onviewchange(view, transformExtent(map.getView().calculateExtent(map.getSize()), map.getView().getProjection(), 'EPSG:4326'));
    });
    map.on('change:size', () => map.setPixelRatio(displayPixelRatio(window.devicePixelRatio, map.getSize() || [1, 1], lowDetail)));
    map.on('singleclick', e => {
      const cluster = map.forEachFeatureAtPixel(e.pixel, feature => feature, { layerFilter: layer => layer === stationLayer, hitTolerance: 6 });
      if (cluster) {
        const members = cluster.get('features') as Feature<Point>[];
        if (members.length === 1) { onstation(members[0].get('station')); return; }
        const coordinates = members.map(f => f.getGeometry()!.getCoordinates());
        const extent = [Math.min(...coordinates.map(p => p[0])), Math.min(...coordinates.map(p => p[1])), Math.max(...coordinates.map(p => p[0])), Math.max(...coordinates.map(p => p[1]))];
        if ((map.getView().getZoom() || 0) >= 15 || Math.max(extent[2]-extent[0],extent[3]-extent[1]) < 1) onstationcluster(members.map(f => f.get('station')));
        else map.getView().fit(extent, { padding: [70,70,170,70], maxZoom: 15, duration: 250 });
        return;
      }
      onpick(toLonLat(e.coordinate, map.getView().getProjection()));
    });
    map.on('pointermove', e => { if (!e.dragging) target.style.cursor = map.hasFeatureAtPixel(e.pixel, { layerFilter: layer => layer === stationLayer, hitTolerance: 6 }) ? 'pointer' : ''; });
    mounted = true;
    return () => { mounted = false; cancelAnimationFrame(satelliteStatusFrame); satelliteLayer.getSource()?.dispose(); models.dispose(); map.setTarget(undefined); map.dispose(); };
  });

  function queueSatelliteStatus() {
    if (!mounted || satelliteStatusFrame) return;
    satelliteStatusFrame = requestAnimationFrame(() => { satelliteStatusFrame = 0; updateSatelliteStatus(); });
  }
  function updateSatelliteStatus() {
    if (!mounted) return;
    const view = map.getView(), source = satelliteLayer.getSource();
    const zoomedOut = (view.getZoom() ?? 0) < HLS_MIN_ZOOM;
    const resolution = view.getResolution();
    if (satellite.enabled && source && resolution && !zoomedOut) {
      onsatellitestatus(source.status(view.calculateExtent(map.getSize()), resolution), false);
      onsatellitepick(point ? source.sample(fromLonLat(point), resolution) : null);
    } else {
      onsatellitestatus({ pending: 0, loaded: 0, empty: 0, failed: 0 }, zoomedOut);
      onsatellitepick(satellite.enabled && point && zoomedOut ? { state: 'zoom' } : null);
    }
  }
  function setSatellite(settings: HlsSettings, revision: number) {
    // Opacity updates reuse cached tiles. Disabling/date/view changes abort old work.
    const window = hlsWindow(settings);
    const key = settings.enabled ? JSON.stringify([window, settings.view, revision]) : '';
    if (key !== satelliteKey) {
      satelliteKey = key;
      const old = satelliteLayer.getSource();
      satelliteLayer.setSource(null); old?.dispose();
      if (settings.enabled) satelliteLayer.setSource(new HlsSource(window, settings.view, queueSatelliteStatus));
    }
    satelliteLayer.setVisible(settings.enabled);
    satelliteLayer.setOpacity(settings.opacity);
    queueSatelliteStatus();
  }

  function rememberRenderer(preference: RendererPreference) {
    try { localStorage.setItem(RENDERER_STORAGE_KEY, preference); } catch { /* Session-only mode. */ }
  }

  function updateMarker() {
    marker.clear();
    if (point) marker.addFeature(new Feature(new Point(fromLonLat(point, map.getView().getProjection()))));
  }

  $: if (mounted && !fitted && frames.length) { fit(0); updateMarker(); }
  $: if (mounted) models.show(frames, selectionId);
  $: if (mounted) models.setOpacity(opacity);
  $: if (mounted) models.setHideZero(hideZeroSnow);
  $: if (mounted) {
    point; updateMarker(); queueSatelliteStatus();
  }
  $: if (mounted) {
    setBasemap(basemap);
  }
  $: if (mounted) {
    stationSource.clear();
    stationSource.addFeatures(stations.map(station => new Feature({ geometry: new Point(fromLonLat([station.lon,station.lat])), station })));
  }
  $: if (mounted) stationLayer.setVisible(stationsVisible);
  $: if (mounted) setSatellite(satellite, satelliteRevision);
</script>
<div bind:this={target} class="map-canvas" aria-label="Interactive snowpack map"></div>
