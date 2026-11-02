export interface VatSplitResult {
  netUnitPrice: number;
  netTotal: number;
  tax: number;
  lineTotal: number;
}

const SCALE = 10000n;

// Parse decimal text exactly, including scientific notation from number-valued form controls.
function decimal(value: string | number): { numerator: bigint; denominator: bigint } {
  const match = /^([+-]?)(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i.exec(String(value));
  if (!match) throw new RangeError('Invalid decimal');
  const fraction = match[3] ?? '';
  const exponent = Number(match[4] ?? 0) - fraction.length;
  const digits = BigInt(`${match[1]}${match[2]}${fraction}`);
  return exponent >= 0
    ? { numerator: digits * 10n ** BigInt(exponent), denominator: 1n }
    : { numerator: digits, denominator: 10n ** BigInt(-exponent) };
}

function roundRatio(numerator: bigint, denominator: bigint): bigint {
  const sign = numerator < 0n ? -1n : 1n;
  return sign * ((2n * numerator * sign + denominator) / (2n * denominator));
}

/** Monetary amounts in integer ten-thousandths, with decimal half-up rounding. */
export function moneyUnits(amount: string | number): bigint {
  const value = decimal(amount);
  return roundRatio(value.numerator * SCALE, value.denominator);
}

export function lineNetUnits(unitPrice: string | number, quantity: string | number): bigint {
  const price = decimal(unitPrice);
  const qty = decimal(quantity);
  return roundRatio(price.numerator * qty.numerator * SCALE, price.denominator * qty.denominator);
}

export function formatMoneyUnits(units: bigint): string {
  const absolute = units < 0n ? -units : units;
  return `${units < 0n ? '-' : ''}${absolute / SCALE}.${String(absolute % SCALE).padStart(4, '0')}`;
}

export function splitVatInclusiveLine(
  grossUnit: string,
  quantity: number | string,
  rate: string,
): VatSplitResult {
  const gross = decimal(grossUnit);
  const vat = decimal(rate);
  const qty = decimal(quantity);
  const netUnit = roundRatio(gross.numerator * vat.denominator * SCALE,
    gross.denominator * (vat.denominator + vat.numerator));
  const netTotal = roundRatio(netUnit * qty.numerator, qty.denominator);
  const grossTotal = lineNetUnits(grossUnit, quantity);
  return {
    netUnitPrice: Number(netUnit) / Number(SCALE),
    netTotal: Number(netTotal) / Number(SCALE),
    tax: Number(grossTotal - netTotal) / Number(SCALE),
    lineTotal: Number(grossTotal) / Number(SCALE),
  };
}
