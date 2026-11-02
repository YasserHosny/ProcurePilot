import { sameReviewedValue } from './reviewed-value';

describe('sameReviewedValue', () => {
  describe('money-like vs money-like', () => {
    it('is false when the amounts differ', () => {
      expect(sameReviewedValue({ amount: '80.00', currency: 'GBP' }, { amount: '75.00', currency: 'GBP' })).toBeFalse();
    });

    it('is true when the amounts are numerically equal', () => {
      expect(sameReviewedValue({ amount: '75.00', currency: 'GBP' }, { amount: '75', currency: 'GBP' })).toBeTrue();
    });

    it('is true when one side omits currency entirely', () => {
      expect(sameReviewedValue({ amount: '75.00' }, { amount: '75', currency: 'GBP' })).toBeTrue();
    });

    it('is true when one side has a null currency', () => {
      expect(sameReviewedValue({ amount: '75.00', currency: null }, { amount: '75', currency: 'USD' })).toBeTrue();
    });

    it('is true when both sides omit currency', () => {
      expect(sameReviewedValue({ amount: '75' }, { amount: '75.00' })).toBeTrue();
    });

    it('is false when both currencies are present and differ', () => {
      expect(sameReviewedValue({ amount: '75.00', currency: 'GBP' }, { amount: '75.00', currency: 'USD' })).toBeFalse();
    });

    it('is false when the amounts are non-numeric', () => {
      expect(sameReviewedValue({ amount: 'abc', currency: 'GBP' }, { amount: 'abc', currency: 'GBP' })).toBeFalse();
    });
  });

  describe('money-like vs plain string or number', () => {
    it('is true when the string equals the amount numerically', () => {
      expect(sameReviewedValue('75.00', { amount: '75.00', currency: 'GBP' })).toBeTrue();
    });

    it('is true when the number equals the amount numerically', () => {
      expect(sameReviewedValue({ amount: '75.00', currency: 'GBP' }, 75)).toBeTrue();
    });

    it('is false when the string differs from the amount', () => {
      expect(sameReviewedValue({ amount: '80.00', currency: 'GBP' }, '75.00')).toBeFalse();
    });

    it('is false when the other side is not a plain string or number', () => {
      expect(sameReviewedValue({ amount: '75.00', currency: 'GBP' }, { amount: '75.00' })).toBeTrue();
      expect(sameReviewedValue({ amount: '75.00', currency: 'GBP' }, { other: 1 })).toBeFalse();
    });
  });

  describe('strings and numbers', () => {
    it('compares trimmed strings for equality (dates)', () => {
      expect(sameReviewedValue('2026-08-20', '2026-08-20')).toBeTrue();
      expect(sameReviewedValue('2026-08-20 ', ' 2026-08-20')).toBeTrue();
      expect(sameReviewedValue('2026-08-20', '2026-08-21')).toBeFalse();
    });

    it('compares currency codes as trimmed strings', () => {
      expect(sameReviewedValue('GBP', 'GBP')).toBeTrue();
      expect(sameReviewedValue('GBP', 'gbp')).toBeFalse();
    });

    it('compares a number against its string form', () => {
      expect(sameReviewedValue(75, '75')).toBeTrue();
      expect(sameReviewedValue('80', 75)).toBeFalse();
      // The string/number rule is trimmed string equality, not numeric: only money-like
      // values are compared numerically, so '75.00' (string) and 75 (number) differ.
      expect(sameReviewedValue('75.00', 75)).toBeFalse();
    });
  });

  describe('other objects', () => {
    it('uses JSON.stringify equality', () => {
      expect(sameReviewedValue({ a: 1, b: 2 }, { a: 1, b: 2 })).toBeTrue();
      expect(sameReviewedValue({ a: 1 }, { a: 2 })).toBeFalse();
      expect(sameReviewedValue({ a: 1, b: 2 }, { b: 2, a: 1 })).toBeFalse();
    });
  });

  describe('null and undefined', () => {
    it('treats null and undefined as the same empty value', () => {
      expect(sameReviewedValue(null, null)).toBeTrue();
      expect(sameReviewedValue(undefined, null)).toBeTrue();
      expect(sameReviewedValue(undefined, undefined)).toBeTrue();
    });

    it('treats an empty value as different from any present value', () => {
      expect(sameReviewedValue(null, 'x')).toBeFalse();
      expect(sameReviewedValue(undefined, 0)).toBeFalse();
      expect(sameReviewedValue(null, { amount: '75.00', currency: 'GBP' })).toBeFalse();
    });
  });
});
