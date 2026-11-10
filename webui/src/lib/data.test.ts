import { describe, expect, it } from 'vitest';
import { colorPixel, pixelAt, physicalValue, normalizeCatalogue, seriesCSV } from './data';

describe('scientific point sampling', () => {
  it('inverts north-up and rotated transforms, excluding outer edges', () => {
    expect(pixelAt([101, 199], [2, 0, 100, 0, -2, 200], [10, 10])).toEqual([0, 0]);
    expect(pixelAt([120, 190], [2, 0, 100, 0, -2, 200], [10, 10])).toBeNull();
    expect(pixelAt([107.5, 199.5], [2, 1, 100, 1, -2, 200], [10, 10])).toEqual([2, 1]);
  });
  it('preserves zero and masks nodata before scaling', () => {
    expect(physicalValue(0, -9999, .1, 2)).toBe(2);
    expect(physicalValue(-9999, -9999, .1, 2)).toBeNull();
    expect(physicalValue(NaN, 'NaN', 1, 0)).toBeNull();
  });
  it('exports missing samples as blanks, not zeros', () => {
    const csv = seriesCSV([{ time: '2026-11-05T23:00:00Z', value: null }], [-115, 51], 'mm');
    expect(csv).toContain(',-115,51,,"mm","nodata"');
  });
  it('rejects unsupported catalogues before displaying data', () => {
    expect(() => normalizeCatalogue({ version: 2, variables: [] }, 'https://example.com/catalog.json')).toThrow();
  });
  it('colourizes floating-point data in an isolated raster worker', () => {
    const operation = new Function(`return (${colorPixel.toString()})`)();
    const settings = { min: -10, max: 10, scale: .1, offset: 0, nodata: -9999, colors: [[0, 0, 0], [200, 100, 50]] };
    expect(operation([[0, 255]], settings)).toEqual([100, 50, 25, 255]);
    expect(operation([[-50, 255]], settings)).toEqual([50, 25, 12.5, 255]);
    expect(operation([[0, 0]], settings)).toEqual([0, 0, 0, 0]);
    expect(operation([[-9999, 255]], settings)).toEqual([0, 0, 0, 0]);
  });
});
