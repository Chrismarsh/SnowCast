import DataTileSource from 'ol/source/DataTile';
import { RequestPool } from './rasterRequests';
import {
  HLS_STAC, HLS_MIN_ZOOM, HLS_MAX_ZOOM, HLS_TILE_SIZE, compositeScene, parseScenes,
  sceneTileURL, searchURL, sortScenes, tileBounds,
  type HlsWindow, type HlsScene, type HlsView, type HlsStatus, type HlsPick,
} from './hls';

type Mosaic = { pixels: Uint8ClampedArray; provenance: Uint16Array; scenes: HlsScene[]; dates: string[] };
type TileRecord = { state: 'loading' | 'ready' | 'error'; mosaic?: Omit<Mosaic, 'pixels'>; error?: string };
type Decoder = (blob: Blob) => Promise<Uint8ClampedArray>;
const SIZE = HLS_TILE_SIZE;

async function decodePNG(blob: Blob): Promise<Uint8ClampedArray> {
  const image = await createImageBitmap(blob);
  try {
    if (image.width !== SIZE || image.height !== SIZE) throw new Error('Unexpected satellite image size.');
    const canvas = document.createElement('canvas'); canvas.width = SIZE; canvas.height = SIZE;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) throw new Error('Satellite imagery needs Canvas support.');
    context.drawImage(image, 0, 0);
    return context.getImageData(0, 0, SIZE, SIZE).data;
  } finally { image.close(); }
}

function overlaps(a: number[], b: number[]) {
  return a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1];
}

/** Shared, bounded requests; catalogue pages contain metadata, never signed asset URLs. */
export class HlsClient {
  private controller = new AbortController();
  private pool = new RequestPool(4);
  private searches = new Map<string, Promise<HlsScene[]>>();
  constructor(readonly window: HlsWindow, readonly view: HlsView,
    private fetcher: typeof fetch = fetch, private decode: Decoder = decodePNG) {}

  dispose() { this.controller.abort(); this.searches.clear(); }

  private async request(url: string, signal: AbortSignal, image = false): Promise<Response> {
    return this.pool.run(signal, async () => {
      const response = await this.fetcher.call(globalThis, url, {
        signal: AbortSignal.any([signal, this.controller.signal, AbortSignal.timeout(image ? 45000 : 20000)]),
      });
      // Drain the response inside the pool so bodies and renders count towards the limit.
      const body = await response.blob();
      signal.throwIfAborted();
      return new Response(body, { status: response.status, headers: response.headers });
    });
  }

  private async search(bounds: number[]): Promise<HlsScene[]> {
    const scenes: HlsScene[] = [];
    let url: string | undefined = searchURL(bounds, this.window);
    for (let page = 0; url; page++) {
      if (page >= 5) throw new Error('Too many satellite scenes. Choose a shorter lookback window.');
      const response = await this.request(url, this.controller.signal);
      if (!response.ok) throw new Error(`Satellite catalogue returned HTTP ${response.status}.`);
      const body = await response.json();
      scenes.push(...parseScenes(body.features, this.window));
      const next = body.links?.find((link: { rel?: string }) => link.rel === 'next');
      url = undefined;
      if (next) {
        const target = new URL(next.href, HLS_STAC);
        if (target.origin !== new URL(HLS_STAC).origin || !target.pathname.startsWith('/api/stac/v1/') || (next.method && next.method !== 'GET')) {
          throw new Error('Unsupported satellite catalogue pagination.');
        }
        url = target.href;
      }
    }
    return sortScenes(scenes);
  }

  async mosaic(z: number, x: number, y: number, tileSignal: AbortSignal): Promise<Mosaic> {
    const signal = AbortSignal.any([tileSignal, this.controller.signal]);
    signal.throwIfAborted();
    // Reuse one catalogue search for neighbouring tiles at every display zoom.
    const factor = 2 ** (z - HLS_MIN_ZOOM);
    const sx = Math.floor(x / factor), sy = Math.floor(y / factor), key = `${sx}/${sy}`;
    let search = this.searches.get(key);
    if (!search) {
      search = this.search(tileBounds(HLS_MIN_ZOOM, sx, sy));
      this.searches.set(key, search);
      const current = search;
      void search.catch(() => { if (this.searches.get(key) === current) this.searches.delete(key); });
      while (this.searches.size > 64) this.searches.delete(this.searches.keys().next().value!);
    }
    const bounds = tileBounds(z, x, y);
    const scenes = (await search).filter(s => overlaps(s.bounds, bounds));
    signal.throwIfAborted();
    const pixels = new Uint8ClampedArray(SIZE * SIZE * 4);
    const provenance = new Uint16Array(SIZE * SIZE);
    const dates = new Set<string>();
    let filled = 0;
    for (let i = 0; i < scenes.length && filled < provenance.length; i++) {
      signal.throwIfAborted();
      const response = await this.request(sceneTileURL(scenes[i], this.view, z, x, y), signal, true);
      if (!response.ok) {
        // A projected footprint can miss a tile even when its geographic bbox intersects.
        // Other failures must not silently substitute older snow observations.
        if (response.status === 404 && /outside bounds/i.test(await response.text())) continue;
        throw new Error(`Satellite image request returned HTTP ${response.status}.`);
      }
      if (!response.headers.get('content-type')?.startsWith('image/png')) throw new Error('Satellite service did not return an image.');
      const image = await this.decode(await response.blob());
      signal.throwIfAborted();
      const added = compositeScene(pixels, provenance, image, i);
      if (added) dates.add(scenes[i].datetime.slice(0, 10));
      filled += added;
    }
    return { pixels, provenance, scenes, dates: [...dates].sort() };
  }
}

/** Canvas imagery and per-pixel provenance share exactly the same compositing decision. */
export class HlsSource extends DataTileSource {
  private client: HlsClient;
  private records = new Map<string, TileRecord>();
  private recordLimit = 128;
  constructor(window: HlsWindow, view: HlsView, private onupdate: () => void) {
    super({ projection: 'EPSG:3857', minZoom: HLS_MIN_ZOOM, maxZoom: HLS_MAX_ZOOM,
      tileSize: SIZE, wrapX: false, interpolate: false, transition: 0,
      attributions: 'NASA/USGS HLS · Copernicus Sentinel-2 · <a href="https://planetarycomputer.microsoft.com/dataset/group/hls2" target="_blank" rel="noreferrer">Microsoft Planetary Computer</a>' });
    this.client = new HlsClient(window, view);
    this.setLoader(async (z, x, y, { signal }) => {
      const key = `${z}/${x}/${y}`;
      const record: TileRecord = { state: 'loading' };
      this.records.delete(key); this.records.set(key, record);
      // Track OL's viewport-sized image cache, including large desktop displays.
      while (this.records.size > this.recordLimit) this.records.delete(this.records.keys().next().value!);
      this.onupdate();
      try {
        const result = await this.client.mosaic(z, x, y, signal);
        signal.throwIfAborted();
        const canvas = document.createElement('canvas'); canvas.width = SIZE; canvas.height = SIZE;
        const context = canvas.getContext('2d');
        if (!context) throw new Error('Satellite imagery needs Canvas support.');
        const image = context.createImageData(SIZE, SIZE); image.data.set(result.pixels); context.putImageData(image, 0, 0);
        record.state = 'ready';
        record.mosaic = { provenance: result.provenance, scenes: result.scenes, dates: result.dates };
        return canvas;
      } catch (error) {
        if (signal.aborted || this.disposed) this.records.delete(key);
        else { record.state = 'error'; record.error = error instanceof Error && error.name === 'TimeoutError'
          ? 'Satellite service timed out. Retry imagery.' : error instanceof Error ? error.message : 'Satellite imagery could not be loaded.'; }
        throw error;
      } finally { this.onupdate(); }
    });
  }

  status(extent: number[], resolution: number): HlsStatus {
    const result: HlsStatus = { pending: 0, loaded: 0, empty: 0, failed: 0 };
    const grid = this.getTileGrid()!;
    const z = grid.getZForResolution(resolution);
    const range = grid.getTileRangeForExtentAndZ(extent, z);
    this.recordLimit = Math.max(128, Math.min(1024, range.getWidth() * range.getHeight() * 2));
    const dates = new Set<string>();
    for (let x = range.minX; x <= range.maxX; x++) for (let y = range.minY; y <= range.maxY; y++) {
      const record = this.records.get(`${z}/${x}/${y}`);
      if (!record || record.state === 'loading') result.pending++;
      else if (record.state === 'error') { result.failed++; result.error = record.error; }
      else if (!record.mosaic?.dates.length) result.empty++;
      else { result.loaded++; record.mosaic.dates.forEach(d => dates.add(d)); }
    }
    const sorted = [...dates].sort(); result.first = sorted[0]; result.last = sorted.at(-1);
    return result;
  }

  sample(coordinate: number[], resolution: number): HlsPick {
    const grid = this.getTileGrid()!;
    const [z, x, y] = grid.getTileCoordForCoordAndResolution(coordinate, resolution);
    const record = this.records.get(`${z}/${x}/${y}`);
    if (!record || record.state === 'loading') return { state: 'loading' };
    if (record.state === 'error') return { state: 'error' };
    const extent = grid.getTileCoordExtent([z, x, y]);
    const col = Math.max(0, Math.min(SIZE - 1, Math.floor((coordinate[0] - extent[0]) / (extent[2] - extent[0]) * SIZE)));
    const row = Math.max(0, Math.min(SIZE - 1, Math.floor((extent[3] - coordinate[1]) / (extent[3] - extent[1]) * SIZE)));
    const index = record.mosaic!.provenance[row * SIZE + col];
    return index ? { state: 'ready', scene: record.mosaic!.scenes[index - 1] } : { state: 'empty' };
  }

  protected override disposeInternal() { this.client.dispose(); this.records.clear(); super.disposeInternal(); }
}
