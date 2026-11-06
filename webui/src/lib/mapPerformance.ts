/** Bound display work without changing full-resolution point sampling. */
export function displayPixelRatio(deviceRatio: number, size: number[], lowDetail = false): number {
  const area = Math.max(1, size[0] * size[1]);
  const requested = Number.isFinite(deviceRatio) && deviceRatio > 0 ? deviceRatio : 1;
  return Math.min(requested, lowDetail ? 1 : 2, Math.sqrt(4_000_000 / area));
}

/** Tile events include aborted/unneeded tiles; count these as settled, not downloaded. */
export class TileProgress {
  private pending = new Set<unknown>();
  started = 0;
  settled = 0;
  errors = 0;
  lastSettled: number | null = null;

  start(tile: unknown) {
    if (!this.pending.has(tile)) this.started++;
    this.pending.add(tile);
  }
  end(tile: unknown, error = false) {
    this.pending.delete(tile);
    this.settled++;
    if (error) this.errors++;
    this.lastSettled = performance.now();
  }
  snapshot() {
    return {
      started: this.started, pending: this.pending.size, settled: this.settled, errors: this.errors,
      secondsSinceLastSettled: this.lastSettled === null ? null : Math.round((performance.now() - this.lastSettled) / 1000),
    };
  }
}
