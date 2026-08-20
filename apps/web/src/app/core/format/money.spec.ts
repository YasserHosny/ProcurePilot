import { MoneyError, assertSameCurrency, formatMoney, money } from './money';

/**
 * Money is the type the product's north-star metric is denominated in, so its guards are tested
 * rather than assumed.
 */
describe('Money', () => {
  it('accepts a well-formed decimal amount', () => {
    const value = money('12.34', 'GBP');
    expect(value.amount).toBe('12.34');
    expect(value.currency).toBe('GBP');
  });

  it('rejects a float dressed up as an amount', () => {
    // The whole point of a decimal string: 0.1 + 0.2 !== 0.3 in binary floating point, and a
    // savings claim cannot inherit that error.
    expect(() => money(String(0.1 + 0.2), 'GBP')).toThrowError(MoneyError);
  });

  it('rejects amounts that are not decimals', () => {
    expect(() => money('twelve', 'GBP')).toThrowError(MoneyError);
    expect(() => money('', 'GBP')).toThrowError(MoneyError);
    expect(() => money('1.2.3', 'GBP')).toThrowError(MoneyError);
  });

  it('rejects anything that is not an ISO 4217 code', () => {
    expect(() => money('1.00', 'pounds')).toThrowError(MoneyError);
    expect(() => money('1.00', 'gbp')).toThrowError(MoneyError);
  });

  it('refuses to combine different currencies', () => {
    // A category error, not a rounding problem. It must fail loudly rather than produce a
    // plausible-looking wrong total.
    expect(() => assertSameCurrency(money('1.00', 'GBP'), money('1.00', 'EGP'))).toThrowError(
      MoneyError,
    );
  });

  it('allows combining the same currency', () => {
    expect(() => assertSameCurrency(money('1.00', 'GBP'), money('2.00', 'GBP'))).not.toThrow();
  });

  it('formats for display without losing the currency', () => {
    expect(formatMoney(money('1234.50', 'GBP'), 'en-GB')).toContain('£');
  });
});
