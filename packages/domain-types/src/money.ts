/**
 * Money — task T084 (FR-020, Constitution Principle VII).
 *
 * There is no such thing as a bare number for money in this product. Every amount carries its
 * currency, because the entire proposition is comparing offers that arrive in different
 * currencies, pack sizes and tax treatments — and a number that has lost its currency cannot be
 * compared, only guessed at.
 *
 * This type lands BEFORE chunk 4.2 stores its first price, deliberately. Retrofitting currency
 * onto stored amounts means a migration over financial data, which is the most expensive kind.
 */

/** ISO 4217 alphabetic code, e.g. 'GBP'. Validated against the supported set at the boundary. */
export type CurrencyCode = string;

/**
 * A monetary amount.
 *
 * `amount` is a DECIMAL STRING, never a JavaScript number. Binary floating point cannot represent
 * 0.1, so `0.1 + 0.2 !== 0.3`, and a product whose north-star metric is verified savings cannot
 * afford to accumulate that error across a basket. Parse to a decimal type at the point of
 * arithmetic; keep the string everywhere else.
 */
export interface Money {
  readonly amount: string;
  readonly currency: CurrencyCode;
}

/** Matches an optionally-signed decimal with at most 6 fractional digits. */
const DECIMAL_PATTERN = /^-?\d+(\.\d{1,6})?$/;

const ISO_4217_PATTERN = /^[A-Z]{3}$/;

export class MoneyError extends Error {}

/**
 * Build a Money, rejecting anything that is not one.
 *
 * Deliberately strict: silently coercing a malformed amount is how a wrong number reaches a
 * savings claim, and Principle I forbids presenting a figure the system cannot stand behind.
 */
export function money(amount: string, currency: CurrencyCode): Money {
  if (!DECIMAL_PATTERN.test(amount)) {
    throw new MoneyError(
      `Not a valid decimal amount: ${JSON.stringify(amount)}. ` +
        'Amounts are decimal strings, never floats — see packages/domain-types/src/money.ts.',
    );
  }
  if (!ISO_4217_PATTERN.test(currency)) {
    throw new MoneyError(`Not an ISO 4217 currency code: ${JSON.stringify(currency)}`);
  }
  return Object.freeze({ amount, currency });
}

/** True when both sides share a currency. Arithmetic across currencies needs an explicit rate. */
export function isSameCurrency(a: Money, b: Money): boolean {
  return a.currency === b.currency;
}

/**
 * Guard for arithmetic. Adding GBP to EGP is not a rounding problem, it is a category error, and
 * the failure must be loud rather than a plausible-looking wrong total.
 */
export function assertSameCurrency(a: Money, b: Money): void {
  if (!isSameCurrency(a, b)) {
    throw new MoneyError(
      `Cannot combine ${a.currency} with ${b.currency} without an explicit conversion rate.`,
    );
  }
}

/** Format for display in a locale. Never used for storage or comparison. */
export function formatMoney(value: Money, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: value.currency,
  }).format(Number(value.amount));
}
