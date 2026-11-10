import { describe, expect, it, vi } from 'vitest';
import { initialRenderer, RendererSelection } from './renderer';

describe('renderer selection and recovery', () => {
  it('keeps the working browser preference unless an explicit link overrides it', () => {
    expect(initialRenderer(null, 'canvas')).toBe('canvas');
    expect(initialRenderer('auto', 'canvas')).toBe('auto');
    expect(initialRenderer('webgl', 'canvas')).toBe('webgl');
    expect(initialRenderer(null, 'invalid')).toBe('auto');
  });
  it('retries a WebGL failure once and remembers Canvas only after a successful frame', () => {
    const remember = vi.fn();
    const selection = new RendererSelection('auto', true, remember);
    expect(selection.mode).toBe('webgl');
    expect(selection.recover('tile failure')).toBe(true);
    expect(selection.mode).toBe('canvas');
    expect(remember).not.toHaveBeenCalled();
    expect(selection.recover('Canvas also failed')).toBe(false);
    expect(remember).not.toHaveBeenCalled();
    selection.frameReady(); selection.frameReady();
    expect(remember).toHaveBeenCalledExactlyOnceWith('canvas');
  });
  it('preserves explicit comparison modes and devices without WebGL', () => {
    const remember = vi.fn();
    const forced = new RendererSelection('webgl', true, remember);
    expect(forced.recover('failure')).toBe(false);
    const unavailable = new RendererSelection('auto', false, remember);
    expect(unavailable.mode).toBe('canvas');
    expect(unavailable.recover('network failure')).toBe(false);
    unavailable.frameReady();
    expect(remember).not.toHaveBeenCalled();
    expect(new RendererSelection('canvas', true, remember).mode).toBe('canvas');
  });
});
