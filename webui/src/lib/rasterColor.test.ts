import { describe, expect, it } from 'vitest';
import { buildExpression, newEvaluationContext } from 'ol/expr/cpu';
import { ColorType, newParsingContext, type EncodedExpression } from 'ol/expr/expression';
import { newCompilationContext } from 'ol/expr/gpu';
import { expressionToGlsl } from 'ol/render/webgl/compileUtil';
import { rasterColor, colorPixel, physicalValue } from './data';

// Feed band values to OpenLayers' real expression evaluator without a GPU.
function readableBands(expression: EncodedExpression): EncodedExpression {
  if (!Array.isArray(expression)) return expression;
  if (expression[0] === 'band') return ['get', expression[1] === 1 ? 'raw' : 'alpha'];
  return expression.map(readableBands);
}

const cases = [
  { id: 'difference', palette: 'difference' as const, range: [-400, 400] as [number, number], valid: 0 },
  { id: 't', palette: 'temperature' as const, range: [-25, 10] as [number, number], valid: -40 },
  { id: 't:difference', palette: 'temperature-difference' as const, range: [-35, 35] as [number, number], valid: 0 },
  { id: 'swe', palette: 'snow' as const, range: [0, 400] as [number, number], valid: 0 },
  { id: 'snowdepthavg', palette: 'snow' as const, range: [0, 2] as [number, number], valid: 0 },
];

describe.each(cases)('$id transparency', variable => {
  const expression = rasterColor({ nodata: -9999, scale: 1, offset: 0 }, variable);
  const evaluate = buildExpression(readableBands(expression), ColorType, newParsingContext());
  function color(raw: number, alpha: number) {
    const context = newEvaluationContext();
    context.properties = { raw, alpha };
    return evaluate(context) as number[];
  }
  it('hides nodata, NaN, and masked pixels without hiding valid zero or cold data', () => {
    expect(color(-9999, 255)).toEqual([0, 0, 0, 0]);
    expect(color(NaN, 255)).toEqual([0, 0, 0, 0]);
    expect(color(variable.valid, 0)).toEqual([0, 0, 0, 0]);
    expect(color(variable.valid, 255)[3]).toBe(1);
  });
  it('compiles a masked colour expression for the two-band WebGL source', () => {
    const context = newCompilationContext(); context.bandCount = 2;
    const shader = expressionToGlsl(context, expression, ColorType);
    expect(shader).toContain('getBandValue(2.0');
    expect(shader).toContain('-9999.0');
    expect(shader).toContain('vec4(0.0, 0.0, 0.0, 0.0)');
  });
  it('matches Canvas missing-data behavior', () => {
    const settings = { min: variable.range[0], max: variable.range[1], scale: 1, offset: 0, nodata: -9999, colors: [[40, 75, 163], [184, 53, 61]] };
    expect(colorPixel([[-9999, 255]], settings)[3]).toBe(0);
    expect(colorPixel([[variable.valid, 0]], settings)[3]).toBe(0);
    expect(colorPixel([[variable.valid, 255]], settings)[3]).toBe(255);
  });
  it('optionally hides only zero absolute snow in both renderers', () => {
    const expression = rasterColor({ nodata: -9999, scale: 1, offset: 0 }, variable, true);
    const evaluate = buildExpression(readableBands(expression), ColorType, newParsingContext());
    const context = newEvaluationContext();
    const settings = { min: variable.range[0], max: variable.range[1], scale: 1, offset: 0, nodata: -9999, colors: [[40, 75, 163], [184, 53, 61]], hideZero: variable.palette === 'snow' };
    for (const raw of [0, -0, 0.00001, -1, 10, NaN, -9999]) {
      context.properties = { raw, alpha: 255 };
      const visible = Number.isFinite(raw) && raw !== -9999 && !(variable.palette === 'snow' && raw === 0);
      expect((evaluate(context) as number[])[3]).toBe(visible ? 1 : 0);
      expect(colorPixel([[raw, 255]], settings)[3]).toBe(visible ? 255 : 0);
    }
    const gpu = newCompilationContext(); gpu.bandCount = 2;
    expect(() => expressionToGlsl(gpu, expression, ColorType)).not.toThrow();
  });
});

describe('zero snow in scaled rasters', () => {
  it.each([true, false])('uses physical zero with masking %s and preserves sampled zeros', hideZero => {
    const asset = { nodata: -9999, scale: 0.5, offset: -1 };
    const variable = { palette: 'snow' as const, range: [0, 400] as [number, number] };
    const evaluate = buildExpression(readableBands(rasterColor(asset, variable, hideZero)), ColorType, newParsingContext());
    const context = newEvaluationContext();
    const settings = { ...asset, min: 0, max: 400, hideZero, colors: [[40, 75, 163], [184, 53, 61]] };
    // raw 2 represents no snow; raw 0 is nonzero after the offset.
    for (const raw of [0, 2, 3]) {
      context.properties = { raw, alpha: 255 };
      expect((evaluate(context) as number[])[3]).toBe(hideZero && raw === 2 ? 0 : 1);
      expect(colorPixel([[raw, 255]], settings)[3]).toBe(hideZero && raw === 2 ? 0 : 255);
    }
    expect(physicalValue(2, asset.nodata, asset.scale, asset.offset)).toBe(0);
  });
});
