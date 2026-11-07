export const SLOW_FRAME_MS = 15_000;
export const STALLED_FRAME_MS = 90_000;

/** A slow transfer is not a failure. Only fail after sustained inactivity. */
export function watchFrameLoad(onSlow: () => void, onStall: () => void) {
  let stopped = false;
  let stallTimer: ReturnType<typeof setTimeout>;
  const slowTimer = setTimeout(() => { if (!stopped) onSlow(); }, SLOW_FRAME_MS);

  const cancel = () => {
    stopped = true;
    clearTimeout(slowTimer);
    clearTimeout(stallTimer);
  };
  const progress = () => {
    if (stopped) return;
    clearTimeout(stallTimer);
    stallTimer = setTimeout(() => { cancel(); onStall(); }, STALLED_FRAME_MS);
  };
  progress();
  return { progress, cancel };
}
