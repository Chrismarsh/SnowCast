import { afterEach, describe, expect, it, vi } from 'vitest';
import { errorDetail, RasterRequests, RequestPool, TileFailures } from './rasterRequests';

const headers = { Range: 'bytes=0-3' };
const url = 'https://example.test/data.tif?secret=hidden';
function partial(bytes = [1, 2, 3, 4]) {
  return new Response(new Uint8Array(bytes), { status: 206, headers: { 'Content-Range': 'bytes 0-3/4' } });
}
function setup(fetcher: typeof fetch, pool = new RequestPool()) {
  const frame = new AbortController(), tile = new AbortController();
  const requests = new RasterRequests(frame.signal, pool, fetcher);
  return { frame, tile, requests, load: () => requests.load(url, headers, tile.signal) };
}
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('COG byte-range requests', () => {
  it('calls the browser fetch with its global receiver', async () => {
    const browserFetch = vi.fn(function (this: unknown) {
      if (this !== globalThis) throw new TypeError("'fetch' called on an object that does not implement interface Window.");
      return Promise.resolve(partial());
    });
    vi.stubGlobal('fetch', browserFetch);
    const requests = new RasterRequests(new AbortController().signal, new RequestPool());
    const response = await requests.load(url, headers, new AbortController().signal);
    expect(Array.from(new Uint8Array(await response.arrayBuffer()))).toEqual([1, 2, 3, 4]);
    expect(browserFetch).toHaveBeenCalledOnce();
    expect(requests.snapshot()).toMatchObject({ completed: 1, retries: 0, failed: 0 });
  });

  it('recovers a temporary HTTP failure before it becomes a failed map tile', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(null, { status: 503 })).mockResolvedValueOnce(partial());
    const { requests, load } = setup(fetcher);
    const result = load();
    await vi.runAllTimersAsync();
    expect(Array.from(new Uint8Array(await (await result).arrayBuffer()))).toEqual([1, 2, 3, 4]);
    expect(requests.snapshot()).toMatchObject({ attempts: 2, completed: 1, retries: 1, failed: 0, active: 0, queued: 0,
      lastError: { phase: 'response', status: 503 } });
  });

  it('retries interrupted bodies as well as failures before response headers', async () => {
    vi.useFakeTimers();
    const interrupted = partial();
    vi.spyOn(interrupted, 'arrayBuffer').mockRejectedValue(new TypeError('Connection reset'));
    const fetcher = vi.fn<typeof fetch>().mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(interrupted).mockResolvedValueOnce(partial());
    const { requests, load } = setup(fetcher);
    const result = load(); await vi.runAllTimersAsync(); await result;
    expect(requests.snapshot()).toMatchObject({ attempts: 3, retries: 2, completed: 1, lastError: { phase: 'body' } });
  });

  it('rejects truncated ranges instead of feeding corrupt bytes into the TIFF decoder', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => partial([1, 2]));
    const { requests, load } = setup(fetcher);
    const rejected = expect(load()).rejects.toThrow('truncated');
    await vi.runAllTimersAsync(); await rejected;
    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(requests.snapshot()).toMatchObject({ failed: 1, retries: 2, active: 0, queued: 0 });
  });

  it.each([404, 416, 200])('does not retry permanent HTTP %s or download a whole COG', async status => {
    const response = new Response(null, { status });
    const body = vi.spyOn(response, 'arrayBuffer');
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response);
    const { requests, load } = setup(fetcher);
    await expect(load()).rejects.toThrow(`HTTP ${status}`);
    expect(fetcher).toHaveBeenCalledOnce();
    expect(body).not.toHaveBeenCalled();
    expect(requests.snapshot().lastError).toMatchObject({ status });
  });

  it('cancels a retry when its frame is abandoned', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Network failure'));
    const { frame, load, requests } = setup(fetcher);
    const result = load();
    const rejected = expect(result).rejects.toThrow('Abandoned frame');
    await vi.advanceTimersByTimeAsync(1);
    frame.abort(new Error('Abandoned frame'));
    await vi.runAllTimersAsync(); await rejected;
    expect(fetcher).toHaveBeenCalledOnce();
    expect(requests.snapshot()).toMatchObject({ cancelled: 1, failed: 0 });
  });

  it('accepts a shorter range at EOF, but rejects the wrong byte offset', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(partial()).mockResolvedValueOnce(
      new Response(new Uint8Array([1, 2, 3, 4]), { status: 206, headers: { 'Content-Range': 'bytes 4-7/8' } }));
    const { requests, tile } = setup(fetcher);
    expect((await requests.load(url, { Range: 'bytes=0-1023' }, tile.signal)).status).toBe(206);
    await expect(requests.load(url + '&revision=2', headers, tile.signal)).rejects.toThrow('Content-Range');
    expect(requests.snapshot()).toMatchObject({ completed: 1, failed: 1, retries: 0 });
  });

  it('limits concurrent transfers and removes an abandoned queued request', async () => {
    const pool = new RequestPool(1);
    let complete!: (r: Response) => void;
    const fetcher = vi.fn<typeof fetch>().mockImplementationOnce(() => new Promise(resolve => { complete = resolve; }))
      .mockImplementation(async () => partial());
    const a = setup(fetcher, pool), b = setup(fetcher, pool), c = setup(fetcher, pool);
    const first = a.load(); const abandoned = b.load(); const third = c.load();
    const rejected = expect(abandoned).rejects.toThrow('Cancelled');
    await Promise.resolve();
    expect(fetcher).toHaveBeenCalledOnce();
    b.frame.abort(new Error('Cancelled'));
    complete(partial());
    await Promise.all([first, rejected, third]);
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(b.requests.snapshot()).toMatchObject({ active: 0, queued: 0, attempts: 0 });
  });
});

describe('per-file TIFF metadata cache', () => {
  const data = Uint8Array.from({ length: 128 * 1024 }, (_, i) => i % 251);
  const rangeResponse = (init?: RequestInit) => {
    const range = new Headers(init?.headers).get('Range')!.match(/^bytes=(\d+)-(\d+)$/)!;
    const start = Number(range[1]), end = Math.min(Number(range[2]), data.length - 1);
    return new Response(data.slice(start, end + 1), { status: 206,
      headers: { 'Content-Range': `bytes ${start}-${end}/${data.length}` } });
  };

  it('coalesces header and tile-index reads while keeping tile bytes direct', async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (_url, init) => rangeResponse(init));
    const { requests, tile } = setup(fetcher);
    const read = async (start: number, length: number) => {
      const response = await requests.load(url, { Range: `bytes=${start}-${start + length - 1}` }, tile.signal);
      expect(response.headers.get('Content-Range')).toBe(`bytes ${start}-${start + length - 1}/${data.length}`);
      expect(response.headers.get('Content-Length')).toBe(String(length));
      expect(new Uint8Array(await response.arrayBuffer())).toEqual(data.slice(start, start + length));
    };
    // The measured full-domain view: 8 header reads + 2 index reads per tile.
    for (let i = 0; i < 8; i++) await read(i * 200, 1024);
    await Promise.all(Array.from({ length: 18 }, async (_, i) => {
      await Promise.all([read(16104 + i * 8, 8), read(16248 + i * 4, 4)]);
      const start = 65536 + i * 1024;
      const response = await requests.load(url, { Range: `bytes=${start}-${start + 1023}` }, tile.signal);
      expect(new Uint8Array(await response.arrayBuffer())).toEqual(data.slice(start, start + 1024));
    }));
    expect(fetcher).toHaveBeenCalledTimes(19);
    expect(new Headers(fetcher.mock.calls[0][1]?.headers).get('Range')).toBe('bytes=0-65535');
    expect(requests.snapshot()).toMatchObject({ completed: 19, metadataHits: 43, bytes: 65536 + 18 * 1024, failed: 0 });
  });

  it('lets a cancelled tile stop waiting without aborting another metadata reader', async () => {
    let complete!: (response: Response) => void;
    const fetcher = vi.fn<typeof fetch>().mockImplementation(() => new Promise(resolve => { complete = resolve; }));
    const { requests, tile, load } = setup(fetcher);
    const first = load(), other = new AbortController();
    const second = requests.load(url, { Range: 'bytes=200-207' }, other.signal);
    const cancelled = expect(first).rejects.toThrow('Tile moved out of view');
    await Promise.resolve();
    tile.abort(new Error('Tile moved out of view'));
    await cancelled;
    expect(fetcher.mock.calls[0][1]?.signal?.aborted).toBe(false);
    complete(rangeResponse({ headers: { Range: 'bytes=0-65535' } }));
    expect(new Uint8Array(await (await second).arrayBuffer())).toEqual(data.slice(200, 208));
    expect(fetcher).toHaveBeenCalledOnce();
  });

  it('does not reuse a failed prefix and keeps URLs and request headers separate', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockImplementation(async (_url, init) => rangeResponse(init));
    const { requests, tile, load } = setup(fetcher);
    await expect(load()).rejects.toThrow('HTTP 404');
    await load();
    await requests.load(url + '&revision=2', headers, tile.signal);
    await requests.load(url + '&revision=2', { ...headers, Authorization: 'test' }, tile.signal);
    expect(fetcher).toHaveBeenCalledTimes(4);
  });

  it('clips short files at EOF and forwards unsatisfiable or crossing ranges', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(partial())
      .mockResolvedValueOnce(new Response(null, { status: 416 }))
      .mockImplementation(async (_url, init) => rangeResponse(init));
    const { requests, tile } = setup(fetcher);
    const short = await requests.load(url, { Range: 'bytes=2-1023' }, tile.signal);
    expect(short.headers.get('Content-Range')).toBe('bytes 2-3/4');
    expect(new Uint8Array(await short.arrayBuffer())).toEqual(new Uint8Array([3, 4]));
    await expect(requests.load(url, { Range: 'bytes=4-7' }, tile.signal)).rejects.toThrow('HTTP 416');
    await requests.load(url, { Range: 'bytes=65530-65540' }, tile.signal);
    expect(new Headers(fetcher.mock.calls[2][1]?.headers).get('Range')).toBe('bytes=65530-65540');
  });

  it('does not serve cached bytes after the frame is disposed', async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (_url, init) => rangeResponse(init));
    const { frame, load } = setup(fetcher);
    await load(); frame.abort(new Error('Disposed'));
    await expect(load()).rejects.toThrow('Disposed');
    expect(fetcher).toHaveBeenCalledOnce();
  });
});

it('retains decoder errors without signed URLs and blocks incomplete raster frames', () => {
  const errors = new TileFailures(), tile = {};
  errors.error(tile, new Error(`Failed to decode ${url}`));
  expect(errors.clear).toBe(false);
  expect(errors.snapshot()).toEqual({ failed: 1, lastError: { name: 'Error', message: 'Failed to decode [URL]' } });
  errors.start(tile);
  expect(errors.clear).toBe(true);
  expect(errorDetail(new TypeError('Invalid typed array length'))).toEqual({ name: 'TypeError', message: 'Invalid typed array length' });
});
