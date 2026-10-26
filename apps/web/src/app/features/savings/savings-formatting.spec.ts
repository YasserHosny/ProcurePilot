import {
  getDeltaClass,
  isNegativeSaving,
  isPositiveSaving,
} from './savings-formatting';

describe('savings-formatting (PPS-66)', () => {
  describe('getDeltaClass', () => {
    it('treats sub-cent amounts and negative zero as zero-delta', () => {
      expect(getDeltaClass({ amount: '-0.0020', currency: 'SAR' })).toBe('zero-delta');
      expect(getDeltaClass({ amount: '-0.0000', currency: 'SAR' })).toBe('zero-delta');
      expect(getDeltaClass({ amount: '0.0040', currency: 'SAR' })).toBe('zero-delta');
    });

    it('correctly classifies real negative and positive deltas', () => {
      expect(getDeltaClass({ amount: '-12.5000', currency: 'SAR' })).toBe('negative-delta');
      expect(getDeltaClass({ amount: '0.0100', currency: 'SAR' })).toBe('positive-delta');
    });
  });

  describe('isNegativeSaving and isPositiveSaving boundaries', () => {
    it('returns false for amounts within the half-cent zero boundary', () => {
      expect(isNegativeSaving({ amount: '-0.0020', currency: 'SAR' })).toBeFalse();
      expect(isPositiveSaving({ amount: '0.0040', currency: 'SAR' })).toBeFalse();
    });
  });
});
