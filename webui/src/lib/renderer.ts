export type RendererPreference = 'auto' | 'webgl' | 'canvas';
export const RENDERER_STORAGE_KEY = 'snowcast-renderer';

export function isRendererPreference(value: string | null): value is RendererPreference {
  return value === 'auto' || value === 'webgl' || value === 'canvas';
}

export function initialRenderer(requested: string | null, saved: string | null): RendererPreference {
  if (isRendererPreference(requested)) return requested;
  return isRendererPreference(saved) ? saved : 'auto';
}

/** One recovery attempt per page; only remember a recovery that actually renders. */
export class RendererSelection {
  mode: 'webgl' | 'canvas';
  fallbackReason: string | null = null;
  private rememberOnReady = false;

  constructor(readonly preference: RendererPreference, webglAvailable: boolean,
    private remember: (preference: RendererPreference) => void) {
    this.mode = webglAvailable && preference !== 'canvas' ? 'webgl' : 'canvas';
  }

  recover(reason: string): boolean {
    if (this.preference !== 'auto' || this.mode !== 'webgl') return false;
    this.mode = 'canvas';
    this.fallbackReason = reason;
    this.rememberOnReady = true;
    return true;
  }

  frameReady() {
    if (!this.rememberOnReady) return;
    this.rememberOnReady = false;
    this.remember('canvas');
  }
}
