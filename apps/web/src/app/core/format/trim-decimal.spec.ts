import { trimDecimal } from './trim-decimal';

describe('trimDecimal', () => {
  for (const [value, expected] of [
    ['50.000000', '50'],
    ['12.500000', '12.5'],
    ['999999999999.999999', '999999999999.999999'],
    ['0.000000', '0'],
    ['100', '100'],
    ['0.000001', '0.000001'],
  ]) {
    it(`trims ${value} to ${expected} without losing precision`, () => {
      expect(trimDecimal(value)).toBe(expected);
    });
  }
});
