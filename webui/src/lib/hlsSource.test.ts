import { describe, expect, it, vi } from 'vitest';
import { HlsClient } from './hlsSource';
import { HLS_STAC } from './hls';
const window = { start: '2026-11-04', end: '2026-11-10' };
const feature = (id: string, collection = 'hls2-s30', day = '2026-11-08') => ({ id, collection, bbox: [-118.2, 48.8, -115, 51], properties: { datetime: `${day}T19:00:00Z`, platform: collection === 'hls2-s30' ? 'sentinel-2c' : 'landsat-8' } });
const page = (features: unknown[], links: unknown[] = []) => Response.json({ features, links });
const png = (name: string) => new Response(name, { headers: { 'Content-Type': 'image/png' } });
const decode = async (blob: Blob) => {
  const label = await blob.text();
  const pixels = new Uint8ClampedArray(256 * 256 * 4);
  pixels.set(label === 'new' ? [100, 101, 102, 255] : [20, 21, 22, 255]);
  if (label === 'old') pixels.set([40, 41, 42, 255], 4);
  return pixels;
};

describe('HLS catalogue and mosaic requests', () => {
  it('paginates, orders both collections by acquisition time, and fills only cloudy gaps', async () => {
    const fetcher = vi.fn(async (url: string | URL | Request) => {
      const u = new URL(String(url));
      if (u.pathname.endsWith('/search')) return u.searchParams.has('token')
        ? page([feature('new', 'hls2-l30', '2026-11-09')])
        : page([feature('old')], [{ rel: 'next', href: `${HLS_STAC}/search?token=next`, method: 'GET' }]);
      return png(u.searchParams.get('item')!);
    });
    const client = new HlsClient(window, 'true-color', fetcher as typeof fetch, decode);
    const result = await client.mosaic(10, 181, 347, new AbortController().signal);
    expect(result.scenes.map(s => s.id)).toEqual(['new', 'old']);
    expect([...result.pixels.slice(0, 12)]).toEqual([100, 101, 102, 255, 40, 41, 42, 255, 0, 0, 0, 0]);
    expect([...result.provenance.slice(0, 3)]).toEqual([1, 2, 0]);
    expect(result.dates).toEqual(['2026-11-08', '2026-11-09']);
    await client.mosaic(10, 181, 347, new AbortController().signal);
    expect(fetcher.mock.calls.filter(c => String(c[0]).includes('/search'))).toHaveLength(2);
    client.dispose();
  });
  it('treats an empty catalogue as transparent missing coverage', async () => {
    const fetcher = vi.fn(async () => page([]));
    const client = new HlsClient(window, 'snow', fetcher as typeof fetch, decode);
    const result = await client.mosaic(10, 181, 347, new AbortController().signal);
    expect(result.dates).toEqual([]); expect(result.provenance.some(Boolean)).toBe(false);
    expect(fetcher).toHaveBeenCalledTimes(1); client.dispose();
  });
  it.each([429, 500, 404])('does not silently fall back to older snow on an HTTP %i failure', async status => {
    const fetcher = vi.fn(async (url: string | URL | Request) => String(url).includes('/search')
      ? page([feature('new', 'hls2-l30', '2026-11-09'), feature('old')]) : new Response('Failed', { status }));
    const client = new HlsClient(window, 'snow', fetcher as typeof fetch, decode);
    await expect(client.mosaic(10, 181, 347, new AbortController().signal)).rejects.toThrow(`HTTP ${status}`);
    expect(fetcher).toHaveBeenCalledTimes(2); client.dispose();
  });
  it('allows a projected footprint miss but rejects a non-image response', async () => {
    const fetcher = vi.fn(async (url: string | URL | Request) => String(url).includes('/search')
      ? page([feature('new', 'hls2-l30', '2026-11-09'), feature('old')])
      : new URL(String(url)).searchParams.get('item') === 'new'
        ? new Response('{"detail":"Tile is outside bounds"}', { status: 404 }) : png('old'));
    const client = new HlsClient(window, 'snow', fetcher as typeof fetch, decode);
    const result = await client.mosaic(10, 181, 347, new AbortController().signal);
    expect(result.provenance[0]).toBe(2); client.dispose();
    const bad = new HlsClient(window, 'snow', (async (url: string) => url.includes('/search') ? page([feature('old')]) : new Response('<html>')) as typeof fetch, decode);
    await expect(bad.mosaic(10, 181, 347, new AbortController().signal)).rejects.toThrow('did not return an image'); bad.dispose();
  });
  it('cancels superseded requests and refuses incomplete or foreign pagination', async () => {
    const controller = new AbortController(); controller.abort();
    const fetcher = vi.fn(async () => page([]));
    const client = new HlsClient(window, 'snow', fetcher as typeof fetch, decode);
    await expect(client.mosaic(10, 181, 347, controller.signal)).rejects.toThrow(); expect(fetcher).not.toHaveBeenCalled(); client.dispose();
    for (const href of [`${HLS_STAC}/search?loop=1`, 'https://example.com/search']) {
      const loop = new HlsClient(window, 'snow', (async () => page([], [{ rel: 'next', href }])) as typeof fetch, decode);
      await expect(loop.mosaic(10, 181, 347, new AbortController().signal)).rejects.toThrow(href.includes('example') ? 'pagination' : 'shorter'); loop.dispose();
    }
  });
});
