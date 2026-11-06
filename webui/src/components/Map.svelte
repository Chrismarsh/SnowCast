<script lang="ts">
  import { onMount } from 'svelte';
  import OLMap from 'ol/Map';
  import View from 'ol/View';
  import TileLayer from 'ol/layer/Tile';
  import WebGLTile from 'ol/layer/WebGLTile';
  import ImageLayer from 'ol/layer/Image';
  import RasterSource from 'ol/source/Raster';
  import GeoTIFF from 'ol/source/GeoTIFF';
  import XYZ from 'ol/source/XYZ';
  import VectorLayer from 'ol/layer/Vector';
  import VectorSource from 'ol/source/Vector';
  import Feature from 'ol/Feature';
  import Point from 'ol/geom/Point';
  import { Circle, Fill, Stroke, Style } from 'ol/style';
  import { fromLonLat, toLonLat, transformExtent } from 'ol/proj';
  import { intersects } from 'ol/extent';
  import { defaults } from 'ol/control';
  import { unByKey } from 'ol/Observable';
  import type { Asset, Variable } from '../lib/types';
  import { ensureProjection } from '../lib/raster';
  import { colorPixel, snowColors, temperatureColors } from '../lib/data';
  import { watchFrameLoad } from '../lib/frameLoad';
  import { displayPixelRatio, TileProgress } from '../lib/mapPerformance';
  import 'ol/ol.css';
  export let asset: Asset | undefined;
  export let variable: Variable | undefined;
  export let opacity = 0.7;
  export let point: number[] | null = null;
  export let bounds = [-116.65, 50.66, -114.77, 51.79];
  export let basemap = 'terrain';
  export let onpick: (point: number[]) => void;
  export let onready: (id: string) => void;
  export let onerror: (error: string) => void;
  export let onslow: (id: string) => void = () => {};
  let target: HTMLDivElement;
  let map: OLMap;
  let mounted = false;
  let marker: VectorSource;
  let base: TileLayer<XYZ>;
  type RasterLayer = WebGLTile | ImageLayer<RasterSource>;
  let active: RasterLayer | undefined;
  let activeVariable = '';
  let useWebGL = true;
  let requested = '';
  let cancel: (() => void) | undefined;
  let fitted = false;
  let baseProgress = new TileProgress();
  let baseMode = '';
  let lastFailure: Record<string, unknown> | undefined;
  const options = new URLSearchParams(window.location.search);
  const lowDetail = options.get('detail') === 'low';
  const withoutBasemap = options.get('basemap') === 'none';
  const layers = new globalThis.Map<string, RasterLayer>();
  const sources = new globalThis.Map<string, GeoTIFF>();
  const requests = new globalThis.Map<string, AbortController>();
  const progress = new globalThis.Map<string, TileProgress>();

  export function fit(duration = 400) { if (map) map.getView().fit(transformExtent(bounds, 'EPSG:4326', map.getView().getProjection()), { padding: [65, 30, 165, 30], duration }); }
  export function zoom(delta: number) { if (map) map.getView().animate({ zoom: (map.getView().getZoom() || 8) + delta, duration: 200 }); }
  export function retry() { if (asset && variable) show(asset, variable); }

  export function diagnostics() {
    return JSON.stringify(lastFailure || snapshotDiagnostics(), null, 2);
  }

  function snapshotDiagnostics() {
    const source = sources.get(requested);
    const layer = layers.get(requested);
    // Deliberately omit URLs, signed query strings, coordinates and GPU identifiers.
    return {
      renderer: useWebGL ? 'WebGL' : 'Canvas', detail: lowDetail ? 'low' : 'automatic',
      viewport: map?.getSize(), devicePixelRatio: window.devicePixelRatio, mapPixelRatio: map?.getPixelRatio(),
      projection: map?.getView().getProjection().getCode(), rasterProjection: source?.getProjection()?.getCode(),
      sourceState: source?.getState() || 'not requested',
      rasterRenderComplete: layer instanceof WebGLTile ? layer.getRenderer()?.renderComplete : !!layer?.get('frameReady'),
      rasterTiles: progress.get(requested)?.snapshot(),
      basemap: withoutBasemap ? 'none' : basemap, basemapTiles: baseProgress.snapshot(),
      cachedFrames: layers.size,
    };
  }

  function setBasemap(mode: string) {
    if (baseMode === mode) return;
    baseMode = mode;
    const old = base.getSource();
    baseProgress = new TileProgress();
    const counter = baseProgress;
    const source = new XYZ({ url: mode === 'satellite' ? 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}' : 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', attributions: 'Tiles © Esri — Esri, HERE, Garmin, USGS, NRCan', crossOrigin: 'anonymous', maxZoom: 17 });
    source.on('tileloadstart', e => counter.start(e.tile));
    source.on('tileloadend', e => counter.end(e.tile));
    source.on('tileloaderror', e => counter.end(e.tile, true));
    base.setSource(source);
    old?.dispose();
  }

  onMount(() => {
    const probe = document.createElement('canvas').getContext('webgl2');
    useWebGL = !!probe && options.get('renderer') !== 'canvas';
    probe?.getExtension('WEBGL_lose_context')?.loseContext();
    base = new TileLayer({ visible: !withoutBasemap });
    marker = new VectorSource();
    map = new OLMap({
      target,
      pixelRatio: displayPixelRatio(window.devicePixelRatio, [target.clientWidth, target.clientHeight], lowDetail),
      controls: defaults({ zoom: false, rotate: false, attributionOptions: { collapsible: false } }),
      layers: [base, new VectorLayer({
        source: marker, zIndex: 50,
        style: new Style({ image: new Circle({ radius: 7, fill: new Fill({ color: '#08777a' }), stroke: new Stroke({ color: 'white', width: 3 }) }) }),
      })],
      // No tile requests until the first asset supplies the actual domain bounds.
      view: new View({ maxZoom: 17 }),
    });
    map.on('change:size', () => map.setPixelRatio(displayPixelRatio(window.devicePixelRatio, map.getSize() || [1, 1], lowDetail)));
    map.on('singleclick', e => onpick(toLonLat(e.coordinate, map.getView().getProjection())));
    mounted = true;
    return () => { cancel?.(); for (const [id, layer] of layers) disposeLayer(id, layer); map.setTarget(undefined); map.dispose(); };
  });

  function disposeLayer(id: string, layer: RasterLayer) {
    requests.get(id)?.abort(); requests.delete(id); progress.delete(id);
    map.removeLayer(layer);
    layer.getSource()?.dispose();
    sources.get(id)?.dispose(); sources.delete(id);
    layer.dispose(); layers.delete(id);
  }

  function updateMarker() {
    marker.clear();
    if (point) marker.addFeature(new Feature(new Point(fromLonLat(point, map.getView().getProjection()))));
  }

  function show(next: Asset, v: Variable) {
    cancel?.();
    lastFailure = undefined;
    requested = next.id;
    try {
      ensureProjection(next.projection, next.proj4);
      if (active && activeVariable !== v.id) { active.setVisible(false); active = undefined; }
      // Canvas fallback keeps data tiles in their native projection; basemap
      // image tiles are reprojected by OpenLayers' Canvas renderer instead.
      if (!useWebGL && map.getView().getProjection().getCode() !== next.projection) {
        map.setView(new View({ projection: next.projection }));
        fitted = false;
      }
      if (!fitted) { fit(0); updateMarker(); fitted = true; }
      let layer = layers.get(next.id);
      if (!layer) {
        const colors = v.palette === 'temperature' ? temperatureColors : snowColors;
        const expression: any[] = ['interpolate', ['linear'], ['+', ['*', ['band', 1], next.scale], next.offset]];
        colors.forEach((color, i) => expression.push(v.range[0] + (v.range[1] - v.range[0]) * i / (colors.length - 1), color));
        const controller = new AbortController();
        requests.set(next.id, controller);
        const cog = new GeoTIFF({ normalize: false, interpolate: false, transition: 0, projection: next.projection, sources: [{ ...(next.blob ? { blob: next.blob } : {
          url: next.href,
          loader: (url, headers, signal) => fetch(url, { headers, signal: AbortSignal.any([signal, controller.signal]) }),
        }), bands: [1], nodata: next.nodata === 'NaN' || next.nodata == null ? NaN : next.nodata }], sourceOptions: { allowFullFile: false, cacheSize: 64 } });
        const counter = new TileProgress();
        progress.set(next.id, counter);
        cog.on('tileloadstart', e => counter.start(e.tile));
        cog.on('tileloadend', e => counter.end(e.tile));
        cog.on('tileloaderror', e => counter.end(e.tile, true));
        sources.set(next.id, cog);
        if (useWebGL) layer = new WebGLTile({ source: cog, style: { color: expression as any }, cacheSize: 64, opacity: 0.01, zIndex: 10 });
        else {
          const raster = new RasterSource({ sources: [cog], interpolate: false, operation: colorPixel });
          raster.on('beforeoperations', e => Object.assign(e.data, {
            colors: colors.map(c => [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]),
            min: v.range[0], max: v.range[1], scale: next.scale, offset: next.offset, nodata: next.nodata,
          }));
          layer = new ImageLayer({ source: raster, opacity: 0.01, zIndex: 10 });
          const canvasLayer = layer;
          raster.on('beforeoperations', () => canvasLayer.set('frameReady', false));
          raster.on('afteroperations', () => { canvasLayer.set('frameReady', true); map.render(); });
        }
        layers.set(next.id, layer);
        map.addLayer(layer);
      }
      const nextLayer = layer;
      if (!useWebGL) { nextLayer.set('frameReady', false); nextLayer.getSource()?.changed(); }
      nextLayer.setVisible(true);
      nextLayer.setOpacity(0.01); // OL rounds opacity to two decimals; zero skips loading.
      let finished = false;
      const source = sources.get(next.id)!;
      const cleanup = () => { watchdog.cancel(); unByKey(readyKey); unByKey(errorKey); unByKey(stateKey); unByKey(progressKey); };
      const fail = (message: string) => {
        if (finished) return;
        finished = true; cleanup();
        lastFailure = { ...snapshotDiagnostics(), capturedAtFailure: message };
        nextLayer.setVisible(nextLayer === active);
        if (nextLayer === active) nextLayer.setOpacity(opacity);
        // A failed source must not poison future retries.
        if (nextLayer !== active) disposeLayer(next.id, nextLayer);
        onerror(message);
      };
      const errorKey = source.on('tileloaderror', () => fail('Could not load this raster. Check its URL, CORS and HTTP range support.'));
      const stateKey = source.on('change', () => {
        if (source.getState() === 'error') fail('The COG could not be opened. Check its projection, format and hosting.');
        else if (source.getState() === 'ready') watchdog.progress();
      });
      const progressKey = source.on('tileloadend', () => watchdog.progress());
      // Map-level rendercomplete also waits for Esri and all other layers.
      // Accept this frame when its own renderer is complete, even if the
      // basemap is still loading. Keep the date unchanged until that point.
      const readyKey = map.on('postrender', () => {
        if (finished || requested !== next.id || source.getState() !== 'ready') return;
        const inView = intersects(map.getView().calculateExtent(map.getSize()), transformExtent(next.bounds, 'EPSG:4326', map.getView().getProjection()));
        if (inView) {
          if (nextLayer instanceof WebGLTile) {
            if (!nextLayer.getRenderer()?.renderComplete) return;
          } else if (!nextLayer.get('frameReady')) return;
        }
        finished = true; cleanup();
        for (const cached of layers.values()) cached.setVisible(cached === nextLayer);
        active = nextLayer; activeVariable = v.id; active.setOpacity(opacity);
        while (layers.size > 3) {
          const entry = [...layers.entries()].find(([key]) => key !== next.id)!;
          disposeLayer(entry[0], entry[1]);
        }
        onready(next.id);
      });
      const watchdog = watchFrameLoad(
        () => onslow(next.id),
        () => fail('No raster loading progress for 90 seconds. Check your connection or retry.'),
      );
      cancel = () => {
        if (finished) return;
        finished = true; cleanup();
        nextLayer.setVisible(nextLayer === active);
        if (nextLayer === active) nextLayer.setOpacity(opacity);
        else disposeLayer(next.id, nextLayer);
      };
      map.render();
    } catch (e) { onerror(e instanceof Error ? e.message : 'Could not display raster'); }
  }

  $: if (mounted && asset && variable && asset.id !== requested) show(asset, variable);
  $: if (active) active.setOpacity(opacity);
  $: if (mounted) {
    point; updateMarker();
  }
  $: if (mounted) {
    setBasemap(basemap);
  }
</script>
<div bind:this={target} class="map-canvas" aria-label="Interactive snowpack map"></div>
