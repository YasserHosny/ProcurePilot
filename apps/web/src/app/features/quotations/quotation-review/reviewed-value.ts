function isMoneyLike(value: unknown): value is { amount: unknown; currency?: unknown } {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    'amount' in value
  );
}

/**
 * Compares a field's effective (corrected) value with its extracted value for review tagging.
 *
 * Money fields hold {amount, currency} objects, so a plain string comparison would stringify
 * both sides to "[object Object]" and label every correction as confirmed-as-is. Money is
 * compared numerically (a missing or null currency matches any currency), plain strings and
 * numbers keep trimmed string equality (dates, currency codes), and any other object falls
 * back to JSON.stringify equality. null/undefined count as the same empty value.
 */
export function sameReviewedValue(a: unknown, b: unknown): boolean {
  const aEmpty = a === null || a === undefined;
  const bEmpty = b === null || b === undefined;
  if (aEmpty || bEmpty) {
    return aEmpty && bEmpty;
  }

  const aMoney = isMoneyLike(a);
  const bMoney = isMoneyLike(b);

  if (aMoney && bMoney) {
    if (Number(a.amount) !== Number(b.amount)) {
      return false;
    }
    const aCurrency = a.currency ?? null;
    const bCurrency = b.currency ?? null;
    if (aCurrency === null || bCurrency === null) {
      return true;
    }
    return String(aCurrency) === String(bCurrency);
  }

  if (aMoney || bMoney) {
    const money = (aMoney ? a : b) as { amount: unknown };
    const other = aMoney ? b : a;
    if (typeof other !== 'string' && typeof other !== 'number') {
      return false;
    }
    return Number(money.amount) === Number(other);
  }

  if (typeof a === 'string' || typeof a === 'number') {
    if (typeof b !== 'string' && typeof b !== 'number') {
      return false;
    }
    return String(a).trim() === String(b).trim();
  }
  if (typeof b === 'string' || typeof b === 'number') {
    return false;
  }

  return JSON.stringify(a) === JSON.stringify(b);
}
