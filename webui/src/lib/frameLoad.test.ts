import { afterEach, describe, expect, it, vi } from 'vitest';
import { SLOW_FRAME_MS, STALLED_FRAME_MS, watchFrameLoad } from './frameLoad';

afterEach(() => vi.useRealTimers());

describe('loading a raster over a slow connection', () => {
  it('keeps a 35-second transfer alive past the former 25-second deadline', () => {
    vi.useFakeTimers();
    const slow = vi.fn(), fail = vi.fn();
    const request = watchFrameLoad(slow, fail);
    vi.advanceTimersByTime(35_000);
    expect(slow).toHaveBeenCalledOnce();
    expect(fail).not.toHaveBeenCalled();
    request.cancel(); // The completed frame is displayed.
    vi.advanceTimersByTime(STALLED_FRAME_MS);
    expect(fail).not.toHaveBeenCalled();
  });

  it('allows a long transfer while tiles continue arriving', () => {
    vi.useFakeTimers();
    const fail = vi.fn();
    const request = watchFrameLoad(vi.fn(), fail);
    for (let i = 0; i < 5; i++) {
      vi.advanceTimersByTime(60_000);
      request.progress();
    }
    expect(fail).not.toHaveBeenCalled();
    vi.advanceTimersByTime(STALLED_FRAME_MS);
    expect(fail).toHaveBeenCalledOnce();
  });

  it('reports a stalled connection once, without reviving its timer', () => {
    vi.useFakeTimers();
    const fail = vi.fn();
    const request = watchFrameLoad(vi.fn(), fail);
    vi.advanceTimersByTime(STALLED_FRAME_MS);
    request.progress();
    vi.advanceTimersByTime(STALLED_FRAME_MS);
    expect(fail).toHaveBeenCalledOnce();
  });

  it('does not let a cancelled date change report errors on the next frame', () => {
    vi.useFakeTimers();
    const oldSlow = vi.fn(), oldFail = vi.fn(), newSlow = vi.fn();
    const old = watchFrameLoad(oldSlow, oldFail);
    old.cancel();
    old.progress(); // Late network event from the cancelled request.
    const current = watchFrameLoad(newSlow, vi.fn());
    vi.advanceTimersByTime(SLOW_FRAME_MS);
    expect(newSlow).toHaveBeenCalledOnce();
    current.cancel();
    vi.advanceTimersByTime(STALLED_FRAME_MS);
    expect(oldSlow).not.toHaveBeenCalled();
    expect(oldFail).not.toHaveBeenCalled();
  });
});
