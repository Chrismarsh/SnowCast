import DataTile, { asArrayLike, disposedError } from 'ol/DataTile';
import DataTileSource from 'ol/source/DataTile';
import TileState from 'ol/TileState';
import { toSize } from 'ol/size';
import { unByKey } from 'ol/Observable';
import type { ViewOptions } from 'ol/View';
import type { Asset } from './types';
import { assertAligned } from './difference';
import { physicalValue } from './data';

/** Separate sources retain each date's validity mask. GeoTIFF's multi-source
 * compositor can keep a pixel if only one source is valid, which is wrong for Δ.
 * Subtract numeric native tiles first, before styling or map reprojection.
 */
export class DifferenceSource extends DataTileSource {
  error = '';
  private stopped = new AbortController();

  constructor(private fromSource: DataTileSource, private toSource: DataTileSource,
    private from: Asset, private to: Asset, signal: AbortSignal) {
    super({ projection: to.projection, bandCount: 2, hasAlpha: true, interpolate: false, transition: 0, state: 'loading' });
    this.nodataBandIndex = 2;
    const lifetime = AbortSignal.any([signal, this.stopped.signal]);
    // getView is also safe for future callers, even if this layer is discarded.
    void this.getView().catch(() => {});
    this.initialize(lifetime).catch(error => {
      this.error = error instanceof Error ? error.message : String(error);
      this.viewRejector?.(error);
      if (!lifetime.aborted) this.setState('error');
    });
  }

  private async initialize(signal: AbortSignal) {
    assertAligned(this.from, this.to);
    const [, view] = await Promise.all([sourceView(this.fromSource, signal), sourceView(this.toSource, signal)]);
    signal.throwIfAborted();
    const a = this.fromSource.getTileGrid()!, b = this.toSource.getTileGrid()!;
    const close = (x: number[], y: number[], tolerance: number) => x.length === y.length && x.every((v, i) => Math.abs(v - y[i]) <= tolerance);
    const tolerance = Math.min(...b.getResolutions()) * 1e-6;
    if (this.fromSource.bandCount !== 2 || this.toSource.bandCount !== 2 ||
        a.getMinZoom() !== b.getMinZoom() || a.getMaxZoom() !== b.getMaxZoom() ||
        !close(a.getResolutions(), b.getResolutions(), tolerance) || !close(a.getExtent()!, b.getExtent()!, tolerance)) {
      throw new Error('These dates have incompatible raster overviews. Republish them on the same grid.');
    }
    const sizes: number[][] = [];
    for (let z = 0; z <= b.getMaxZoom(); z++) {
      if (!close(a.getOrigin(z), b.getOrigin(z), tolerance) || !close(toSize(a.getTileSize(z)), toSize(b.getTileSize(z)), 0)) {
        throw new Error('These dates have incompatible raster tile grids.');
      }
      // Native tile data size can differ from the rendered tile grid size.
      const tileA = this.fromSource.getTile(z, 0, 0, 1), tileB = this.toSource.getTile(z, 0, 0, 1);
      try {
        if (!tileA || !tileB || !close(tileA.getSize(), tileB.getSize(), 0)) throw new Error('These dates have incompatible raster tile sizes.');
        sizes.push([...tileB.getSize()]);
      } finally { tileA?.dispose(); tileB?.dispose(); }
    }
    this.tileGrid = b;
    this.setTileSizes(sizes);
    this.setLoader(async (z, x, y, options) => {
      const tiles = [this.fromSource.getTile(z, x, y, 1), this.toSource.getTile(z, x, y, 1)];
      try {
        if (!tiles[0] || !tiles[1]) throw new Error('A comparison tile is outside its raster grid.');
        const [a, b] = await Promise.all(tiles.map(tile => readTile(tile!, AbortSignal.any([signal, options.signal]))));
        return subtractTiles(a, b, this.from, this.to);
      } finally { tiles.forEach(tile => tile?.dispose()); }
    });
    this.viewResolver?.(view);
    this.setState('ready');
  }

  protected override disposeInternal() {
    this.stopped.abort(disposedError);
    this.fromSource.dispose(); this.toSource.dispose();
    super.disposeInternal();
  }
}

// GeoTIFF can enter ERROR without rejecting getView (e.g. an HTTP metadata
// failure). Observe both so a comparison never waits indefinitely for a date.
function sourceView(source: DataTileSource, signal: AbortSignal): Promise<ViewOptions> {
  return new Promise((resolve, reject) => {
    const cleanup = () => { unByKey(key); signal.removeEventListener('abort', abort); };
    const abort = () => { cleanup(); reject(disposedError); };
    const check = () => {
      if (source.getState() === 'error') { cleanup(); reject(new Error('A comparison COG could not be opened. Check its format and hosting, then retry.')); }
    };
    const key = source.on('change', check);
    signal.addEventListener('abort', abort, { once: true });
    source.getView().then(view => { cleanup(); resolve(view); }, error => { cleanup(); reject(error); });
    if (signal.aborted) abort(); else check();
  });
}

function readTile(tile: DataTile, signal: AbortSignal): Promise<ArrayLike<number>> {
  return new Promise((resolve, reject) => {
    const cleanup = () => { tile.removeEventListener('change', check); signal.removeEventListener('abort', abort); };
    const abort = () => { cleanup(); reject(disposedError); };
    const check = () => {
      if (tile.getState() === TileState.ERROR) { cleanup(); reject(tile.getError()); }
      else if (tile.getState() === TileState.LOADED) {
        cleanup();
        const data = asArrayLike(tile.getData()!);
        if (data && !(data instanceof DataView)) resolve(data);
        else reject(new Error('Expected numeric comparison tiles.'));
      }
    };
    tile.addEventListener('change', check);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) { abort(); return; }
    tile.load(); check();
  });
}

export function subtractTiles(fromData: ArrayLike<number>, toData: ArrayLike<number>, from: Asset, to: Asset): Float32Array {
  if (fromData.length !== toData.length || fromData.length % 2) throw new Error('Comparison tile dimensions do not match.');
  const output = new Float32Array(toData.length);
  for (let i = 0; i < output.length; i += 2) {
    if (!fromData[i + 1] || !toData[i + 1]) continue;
    const a = physicalValue(fromData[i], from.nodata, from.scale, from.offset);
    const b = physicalValue(toData[i], to.nodata, to.scale, to.offset);
    if (a == null || b == null) continue;
    output[i] = b - a;
    if (Number.isFinite(output[i])) output[i + 1] = 255;
    else output[i] = 0;
  }
  return output;
}
