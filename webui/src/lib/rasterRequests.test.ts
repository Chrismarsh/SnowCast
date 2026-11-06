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
afterEach(() => vi.useRealTimers());

describe('COG byte-range requests', () => {
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
    await expect(requests.load(url, headers, tile.signal)).rejects.toThrow('Content-Range');
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

it('retains decoder errors without signed URLs and blocks incomplete raster frames', () => {
  const errors = new TileFailures(), tile = {};
  errors.error(tile, new Error(`Failed to decode ${url}`));
  expect(errors.clear).toBe(false);
  expect(errors.snapshot()).toEqual({ failed: 1, lastError: { name: 'Error', message: 'Failed to decode [URL]' } });
  errors.start(tile);
  expect(errors.clear).toBe(true);
  expect(errorDetail(new TypeError('Invalid typed array length'))).toEqual({ name: 'TypeError', message: 'Invalid typed array length' });
});
