import type OLMap from 'ol/Map';
import WebGLTile from 'ol/layer/WebGLTile';
import ImageLayer from 'ol/layer/Image';
import RasterSource from 'ol/source/Raster';
import GeoTIFF from 'ol/source/GeoTIFF';
import type DataTileSource from 'ol/source/DataTile';
import DataTile, { disposedError } from 'ol/DataTile';
import { transformExtent } from 'ol/proj';
import { intersects } from 'ol/extent';
import { unByKey } from 'ol/Observable';
import type { Asset, Variable } from './types';
import type { ModelFrame } from './projects';
import { DifferenceSource } from './differenceSource';
import { ProjectedRaster } from './projectedRaster';
import { ensureProjection } from './raster';
import { colorPixel, rasterColor, paletteColors } from './data';
import { RasterRequests, RequestPool, TileFailures, rasterSourceOptions } from './rasterRequests';
import { TileProgress } from './mapPerformance';
import { watchFrameLoad } from './frameLoad';
import type { RendererSelection } from './renderer';

type RasterLayer = WebGLTile | ImageLayer<ProjectedRaster>;
interface Entry {
  project: string; layer: RasterLayer; source: DataTileSource; controller: AbortController;
  progress: TileProgress; requests: RasterRequests; failures: TileFailures;
  restyle: (variable: Variable) => void;
}

/** One bounded frame cache per project, sharing a global network request limit. */
export class ModelLayers {
  private entries = new Map<string, Entry>();
  private active = new Set<string>();
  private cancellations: (() => void)[] = [];
  private pool = new RequestPool();
  private generation = 0;
  private key = '';
  private selection = '';
  private frames: ModelFrame[] = [];
  private opacity = .7;
  private hideZero = false;
  private disposed = false;
  private lastFailure: unknown;

  constructor(private map: OLMap, private renderer: RendererSelection, private callbacks: {
    ready: (id: string, errors: string[]) => void; error: (error: string) => void; slow: (id: string) => void;
  }) {}

  diagnostics() {
    return { renderer: this.renderer.mode === 'webgl' ? 'WebGL' : 'Canvas', rendererPreference: this.renderer.preference,
      fallbackReason: this.renderer.fallbackReason, cachedFrames: this.entries.size, lastFailure: this.lastFailure,
      projects: this.frames.map(f => {
        const entry = this.entries.get(f.asset.id);
        return { project: f.project, variable: f.variable.id, frameTime: f.asset.datetime,
          displayed: this.active.has(f.asset.id),
          differenceFrom: f.asset.difference?.from.datetime, rasterProjection: f.asset.projection,
          sourceState: entry?.source.getState(), rasterTiles: entry?.progress.snapshot(),
          rasterRequests: entry?.requests.snapshot(), rasterTileFailures: entry?.failures.snapshot() };
      }) };
  }

  setOpacity(value: number) {
    this.opacity = value;
    for (const id of this.active) this.entries.get(id)?.layer.setOpacity(value);
  }

  setHideZero(value: boolean) {
    if (value === this.hideZero) return;
    this.hideZero = value;
    for (const frame of this.frames) this.entries.get(frame.asset.id)?.restyle(frame.variable);
  }

  private remove(id: string) {
    const entry = this.entries.get(id);
    if (!entry) return;
    entry.controller.abort(); this.map.removeLayer(entry.layer);
    entry.layer.getSource()?.dispose(); entry.source.dispose(); entry.layer.dispose();
    this.entries.delete(id); this.active.delete(id);
  }

  private cancel() { for (const cancel of this.cancellations) cancel(); this.cancellations = []; }

  dispose() {
    this.disposed = true; this.generation++; this.cancel();
    for (const id of [...this.entries.keys()]) this.remove(id);
  }

  retry() {
    this.generation++; this.cancel(); this.key = '';
    for (const frame of this.frames) this.remove(frame.asset.id);
    void this.show(this.frames, this.selection);
  }

  async show(frames: ModelFrame[], selection: string) {
    const key = JSON.stringify([selection, frames.map(f => [f.project, f.asset.id, f.variable.palette, f.variable.range])]);
    if (this.disposed || key === this.key) return;
    this.key = key; this.frames = frames; this.selection = selection;
    const generation = ++this.generation;
    this.cancel(); this.lastFailure = undefined;
    // Hide every old date immediately, including projects absent on this day.
    for (const entry of this.entries.values()) entry.layer.setVisible(false);
    this.active.clear();
    const results = await Promise.all(frames.map((frame, index) => this.load(frame, index, generation)));
    if (this.disposed || generation !== this.generation) return;
    const errors = results.filter((message): message is string => !!message);
    for (const frame of frames) {
      const entry = this.entries.get(frame.asset.id);
      if (entry && entry.failures.clear) {
        entry.layer.setVisible(true); entry.layer.setOpacity(this.opacity); this.active.add(frame.asset.id);
      }
    }
    // Retain at most three dates per project, without evicting another project's active layer.
    for (const project of new Set([...this.entries.values()].map(e => e.project))) {
      const cached = [...this.entries.entries()].filter(([, entry]) => entry.project === project);
      for (const [id] of cached) {
        if (cached.filter(([key]) => this.entries.has(key)).length <= 3) break;
        if (!this.active.has(id)) this.remove(id);
      }
    }
    this.callbacks.ready(selection, errors);
  }

  private create(frame: ModelFrame): Entry {
    const next = frame.asset;
    let variable = frame.variable;
    ensureProjection(next.projection, next.proj4);
    const controller = new AbortController();
    const requests = new RasterRequests(controller.signal, this.pool);
    const failures = new TileFailures(), progress = new TileProgress();
    const open = (a: Asset) => new GeoTIFF({ normalize: false, interpolate: false, transition: 0, projection: a.projection,
      sources: [{ url: a.href, loader: (url, headers, signal) => requests.load(url, headers, signal),
        bands: [1], nodata: a.nodata === 'NaN' || a.nodata == null ? NaN : a.nodata }], sourceOptions: rasterSourceOptions });
    const source = next.difference ? new DifferenceSource(open(next.difference.from), open(next.difference.to),
      next.difference.from, next.difference.to, controller.signal) : open(next);
    source.on('tileloadstart', e => { progress.start(e.tile); failures.start(e.tile); });
    source.on('tileloadend', e => progress.end(e.tile));
    source.on('tileloaderror', e => {
      progress.end(e.tile, true);
      const error = e.tile instanceof DataTile ? e.tile.getError() : new Error('Raster tile failed');
      if (error !== disposedError) failures.error(e.tile, error);
    });
    let layer: RasterLayer;
    let restyle: Entry['restyle'];
    if (this.renderer.mode === 'webgl') {
      const webgl = new WebGLTile({ source, style: { color: rasterColor(next, variable, this.hideZero) }, cacheSize: 64 });
      layer = webgl;
      restyle = v => { variable = v; webgl.setStyle({ color: rasterColor(next, v, this.hideZero) }); };
    } else {
      const raster = new RasterSource({ sources: [source], interpolate: false, operation: colorPixel });
      raster.on('beforeoperations', e => Object.assign(e.data, {
        colors: paletteColors(variable).map(c => [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)]),
        min: variable.range[0], max: variable.range[1], scale: next.scale, offset: next.offset, nodata: next.nodata,
        hideZero: this.hideZero && variable.palette === 'snow',
      }));
      layer = new ImageLayer({ source: new ProjectedRaster(raster, next.projection, () => failures.clear) });
      restyle = v => { variable = v; raster.changed(); };
    }
    // Bound Canvas requests as well as WebGL requests to this project's footprint.
    layer.setExtent(transformExtent(next.bounds, 'EPSG:4326', this.map.getView().getProjection()));
    this.map.addLayer(layer);
    const entry = { project: frame.project, layer, source, controller, progress, requests, failures, restyle };
    this.entries.set(next.id, entry);
    return entry;
  }

  private load(frame: ModelFrame, index: number, generation: number): Promise<string | null> {
    return new Promise(resolve => {
      let entry: Entry;
      try { entry = this.entries.get(frame.asset.id) || this.create(frame); }
      catch (error) { resolve(`${frame.name}: ${error instanceof Error ? error.message : 'Could not open raster'}`); return; }
      const { layer, source } = entry;
      entry.restyle(frame.variable);
      layer.setZIndex(10 + index / Math.max(1, this.frames.length));
      layer.setVisible(true); layer.setOpacity(.01);
      let finished = false;
      const cleanup = (keepErrors = false) => {
        watchdog.cancel(); unByKey(renderKey); unByKey(stateKey); unByKey(progressKey);
        if (!keepErrors) unByKey(errorKey);
      };
      const fail = (message: string, canRecover = false) => {
        if (generation !== this.generation) return;
        const wasReady = finished;
        finished = true; cleanup();
        const detail = `${frame.name}: ${message}`;
        const { lastFailure: _previousFailure, ...snapshot } = this.diagnostics();
        this.lastFailure = { ...snapshot, capturedAtFailure: detail };
        if (canRecover && this.renderer.recover(detail)) {
          this.generation++; this.cancel(); this.key = '';
          for (const id of [...this.entries.keys()]) this.remove(id);
          queueMicrotask(() => { if (!this.disposed) void this.show(this.frames, this.selection); });
        } else {
          this.remove(frame.asset.id);
          if (wasReady) this.callbacks.error(detail);
        }
        resolve(detail);
      };
      const errorKey = source.on('tileloaderror', e => {
        if (!(e.tile instanceof DataTile) || e.tile.getError() !== disposedError)
          fail(entry.failures.snapshot().lastError?.message || 'A raster tile failed', !entry.requests.snapshot().failed);
      });
      const stateKey = source.on('change', () => {
        if (source.getState() === 'error') fail(source instanceof DifferenceSource ? source.error : 'The COG could not be opened');
        else if (source.getState() === 'ready') watchdog.progress();
      });
      const progressKey = source.on('tileloadend', () => watchdog.progress());
      const renderKey = this.map.on('postrender', () => {
        if (finished || generation !== this.generation || source.getState() !== 'ready') return;
        const inView = intersects(this.map.getView().calculateExtent(this.map.getSize()), layer.getExtent()!);
        if (inView && (layer instanceof WebGLTile ? !layer.getRenderer()?.renderComplete : !layer.getSource()?.frameReady)) return;
        finished = true; cleanup(true);
        layer.setOpacity(this.opacity); this.active.add(frame.asset.id);
        if (inView) this.renderer.frameReady();
        resolve(null);
      });
      const watchdog = watchFrameLoad(() => this.callbacks.slow(this.selection),
        () => fail('No raster loading progress for 90 seconds. Retry this date.', true));
      this.cancellations.push(() => { cleanup(); if (!finished) { finished = true; this.remove(frame.asset.id); resolve(null); } });
      if (!entry.failures.clear) fail('A cached raster failed. Retry this date.');
      else if (source.getState() === 'error') fail('The COG could not be opened');
      this.map.render();
    });
  }
}
