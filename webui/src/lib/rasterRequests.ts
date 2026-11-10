/** Keep diagnostic errors useful without including URLs or signed query strings. */
export function errorDetail(error: unknown) {
  const e = error instanceof Error ? error : new Error(String(error));
  return {
    name: e.name,
    message: e.message.replace(/(?:https?:\/\/|blob:|data:)[^\s"'<>]+/gi, '[URL]').slice(0, 300),
  };
}

// OpenLayers' geotiff 3.1.0-beta.0 cache can evict bytes needed by concurrent
// tile reads (reproduced with successful HTTP responses). Explicit undefined
// overrides its default block size and selects direct byte-range reads.
// OpenLayers still caches decoded tiles; browser HTTP caching is unchanged.
// publish_cogs.py keeps square 512px tiles so OL's strip-image fallback does
// not reopen the source with a different blockSize.
export const rasterSourceOptions = { allowFullFile: false, blockSize: undefined };

const METADATA_BYTES = 64 * 1024;
type Metadata = { body: ArrayBuffer; headers: Headers };

/** A tile can stop waiting without cancelling a header shared by other tiles. */
function waitForMetadata(promise: Promise<Metadata>, signal: AbortSignal): Promise<Metadata> {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const abort = () => reject(signal.reason);
    signal.addEventListener('abort', abort, { once: true });
    promise.then(value => {
      signal.removeEventListener('abort', abort); resolve(value);
    }, error => {
      signal.removeEventListener('abort', abort); reject(error);
    });
  });
}

/** Bound COG range requests across the current and cached frames. */
export class RequestPool {
  private active = 0;
  private queue: (() => void)[] = [];
  constructor(private limit = 6) {}

  async run<T>(signal: AbortSignal, operation: () => Promise<T>): Promise<T> {
    signal.throwIfAborted();
    await new Promise<void>((resolve, reject) => {
      const start = () => {
        signal.removeEventListener('abort', abort);
        this.active++;
        resolve();
      };
      const abort = () => {
        this.queue = this.queue.filter(item => item !== start);
        reject(signal.reason);
      };
      if (this.active < this.limit) start();
      else { this.queue.push(start); signal.addEventListener('abort', abort, { once: true }); }
    });
    try { signal.throwIfAborted(); return await operation(); }
    finally { this.active--; this.queue.shift()?.(); }
  }
}

function pause(milliseconds: number, signal: AbortSignal) {
  signal.throwIfAborted();
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, milliseconds);
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    signal.addEventListener('abort', abort, { once: true });
  });
}

class RequestError extends Error {
  constructor(message: string, readonly retryable: boolean, readonly status?: number) { super(message); }
}

export class RasterRequests {
  private attempts = 0;
  private active = 0;
  private queued = 0;
  private completed = 0;
  private retries = 0;
  private failed = 0;
  private cancelled = 0;
  private bytes = 0;
  private lastError: Record<string, unknown> | null = null;
  private metadata = new Map<string, Promise<Metadata>>();
  private metadataHits = 0;

  constructor(private frameSignal: AbortSignal, private pool: RequestPool, private fetcher: typeof fetch = fetch) {}

  snapshot() {
    return { attempts: this.attempts, active: this.active, queued: this.queued,
      completed: this.completed, retries: this.retries, failed: this.failed,
      cancelled: this.cancelled, bytes: this.bytes, metadataHits: this.metadataHits, lastError: this.lastError };
  }

  async load(url: string, headers: HeadersInit, tileSignal: AbortSignal): Promise<Response> {
    const signal = AbortSignal.any([tileSignal, this.frameSignal]);
    signal.throwIfAborted();
    const requestHeaders = new Headers(headers);
    const range = requestHeaders.get('Range')?.match(/^bytes=(\d+)-(\d+)$/);
    if (range && Number(range[1]) <= Number(range[2]) && Number(range[2]) < METADATA_BYTES) {
      // Pin each input file's prefix (two in difference mode). No evictable
      // shared block cache; ranges outside the prefix go directly to the server.
      requestHeaders.delete('Range');
      const key = JSON.stringify([url, [...requestHeaders]]);
      let promise = this.metadata.get(key);
      if (!promise) {
        requestHeaders.set('Range', `bytes=0-${METADATA_BYTES - 1}`);
        promise = this.request(url, requestHeaders, this.frameSignal).then(async response => ({
          body: await response.arrayBuffer(), headers: response.headers,
        }));
        this.metadata.set(key, promise);
        const pending = promise;
        void promise.catch(() => { if (this.metadata.get(key) === pending) this.metadata.delete(key); });
      } else this.metadataHits++;
      const metadata = await waitForMetadata(promise, signal);
      signal.throwIfAborted();
      const start = Number(range[1]);
      const end = Math.min(Number(range[2]), metadata.body.byteLength - 1);
      if (start <= end) {
        const responseHeaders = new Headers(metadata.headers);
        const total = responseHeaders.get('Content-Range')!.split('/')[1];
        responseHeaders.set('Content-Range', `bytes ${start}-${end}/${total}`);
        responseHeaders.set('Content-Length', String(end - start + 1));
        return new Response(metadata.body.slice(start, end + 1), { status: 206, headers: responseHeaders });
      }
      // A request starting beyond EOF must retain the server's 416 behavior.
    }
    return this.request(url, headers, signal);
  }

  private async request(url: string, headers: HeadersInit, signal: AbortSignal): Promise<Response> {
    const range = new Headers(headers).get('Range');
    for (let attempt = 1; ; attempt++) {
      let waiting = true;
      let phase = 'request';
      this.queued++;
      try {
        return await this.pool.run(signal, async () => {
          waiting = false; this.queued--; this.active++; this.attempts++;
          try {
            // Firefox's native fetch requires the global Window receiver.
            const response = await this.fetcher.call(globalThis, url, { headers, signal });
            phase = 'response';
            if (!response.ok || (range && response.status !== 206)) {
              await response.body?.cancel().catch(() => {});
              const retryable = [408, 429, 500, 502, 503, 504].includes(response.status);
              throw new RequestError(range && response.status === 200
                ? 'Server ignored the byte-range request (HTTP 200).'
                : `Raster request returned HTTP ${response.status}.`, retryable, response.status);
            }
            const requested = range?.match(/^bytes=(\d+)-(\d+)$/);
            const received = response.headers.get('Content-Range')?.match(/^bytes (\d+)-(\d+)\/(\d+|\*)$/);
            if (requested && (!received || Number(received[1]) !== Number(requested[1]) ||
                Number(received[2]) !== (received[3] === '*' ? Number(requested[2]) : Math.min(Number(requested[2]), Number(received[3]) - 1)))) {
              await response.body?.cancel().catch(() => {});
              throw new RequestError('Missing or incorrect Content-Range in raster response.', false, response.status);
            }
            // Include body failures in retries; returning fetch() directly only
            // observes response headers and misses interrupted downloads.
            phase = 'body';
            const body = await response.arrayBuffer();
            signal.throwIfAborted();
            if (received && body.byteLength !== Number(received[2]) - Number(received[1]) + 1) {
              throw new RequestError('Raster byte-range response was truncated.', true, response.status);
            }
            this.completed++; this.bytes += body.byteLength;
            return new Response(body, { status: response.status, headers: response.headers });
          } finally { this.active--; }
        });
      } catch (error) {
        if (signal.aborted) { this.cancelled++; throw signal.reason; }
        this.lastError = { ...errorDetail(error), phase, attempt,
          ...(error instanceof RequestError ? { status: error.status } : {}) };
        const retryable = error instanceof RequestError ? error.retryable : error instanceof TypeError;
        if (!retryable || attempt >= 3) { this.failed++; throw error; }
        this.retries++;
        try { await pause(attempt * 400, signal); }
        catch (cancelled) { this.cancelled++; throw cancelled; }
      } finally { if (waiting) this.queued--; }
    }
  }
}

/** Failed tiles must never be interpreted as transparent model nodata. */
export class TileFailures {
  private failed = new Set<unknown>();
  private lastError: ReturnType<typeof errorDetail> | null = null;
  start(tile: unknown) { this.failed.delete(tile); }
  error(tile: unknown, error: unknown) { this.failed.add(tile); this.lastError = errorDetail(error); }
  get clear() { return this.failed.size === 0; }
  snapshot() { return { failed: this.failed.size, lastError: this.lastError }; }
}
