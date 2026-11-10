import { describe, expect, it } from 'vitest';
import { buildExpression, newEvaluationContext } from 'ol/expr/cpu';
import { ColorType, newParsingContext, type EncodedExpression } from 'ol/expr/expression';
import { newCompilationContext } from 'ol/expr/gpu';
import { expressionToGlsl } from 'ol/render/webgl/compileUtil';
import { rasterColor, colorPixel } from './data';

// Feed band values to OpenLayers' real expression evaluator without a GPU.
function readableBands(expression: EncodedExpression): EncodedExpression {
  if (!Array.isArray(expression)) return expression;
  if (expression[0] === 'band') return ['get', expression[1] === 1 ? 'raw' : 'alpha'];
  return expression.map(readableBands);
}

const cases = [
  { id: 'difference', palette: 'difference' as const, range: [-400, 400] as [number, number], valid: 0 },
  { id: 't', palette: 'temperature' as const, range: [-25, 10] as [number, number], valid: -40 },
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
});
