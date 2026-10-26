import { Injectable, inject } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';

import type { Money } from '../api/models';

export type MoneyLike = Money | { amount: string | number; currency: string };

function isArabicLocale(locale: string): boolean {
  return locale.toLowerCase().startsWith('ar');
}

function buildNumberFormatOptions(
  locale: string,
  options?: Intl.NumberFormatOptions,
): Intl.NumberFormatOptions {
  return {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
    ...(isArabicLocale(locale) ? { numberingSystem: 'arab' } : {}),
    ...options,
  };
}

/**
 * Returns the currency symbol for display in user-facing text.
 * For Arabic locales, extracts the Intl currency part without trailing dot or directional marks.
 * For other locales, returns the ISO 4217 currency code.
 * Falls back to the raw code if Intl does not recognize it.
 */
export function currencySymbol(currency: string, locale = 'en'): string {
  if (!currency) return '';
  if (!isArabicLocale(locale)) {
    return currency;
  }
  try {
    const parts = new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
    }).formatToParts(1);
    const currPart = parts.find(p => p.type === 'currency');
    if (!currPart) return currency;
    let s = currPart.value;
    s = s.replace(/[\u200E\u200F\u061C]/g, '');
    s = s.replace(/\.+$/, '');
    return s.trim();
  } catch {
    return currency;
  }
}

/**
 * Pure locale-aware number/quantity formatter: thousands separators, 0-2 fraction digits,
 * and Arabic-Indic digits when locale is 'ar'.
 */
export function formatLocaleNumber(
  value: number | string | null | undefined,
  locale = 'en',
  options?: Intl.NumberFormatOptions,
): string {
  if (value === null || value === undefined || value === '') return '—';

  const num = typeof value === 'number' ? value : parseFloat(value);
  if (isNaN(num)) return '—';

  return new Intl.NumberFormat(locale, buildNumberFormatOptions(locale, options)).format(num);
}

/**
 * Pure locale-aware quantity formatter preserving up to 6 fraction digits
 * (for numeric(18,6) values), trimming trailing zeroes, and Arabic-Indic digits when locale is 'ar'.
 */
export function formatExactQuantity(
  value: number | string | null | undefined,
  locale = 'en',
): string {
  if (typeof value !== 'string' || !/^-?\d+(\.\d+)?$/.test(value)) {
    return formatLocaleNumber(value, locale, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 6,
    });
  }

  const options = buildNumberFormatOptions(locale, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 6,
  });
  const nf = new Intl.NumberFormat(locale, options);
  const parts = nf.formatToParts(-1234.5);
  const group = parts.find(p => p.type === 'group')?.value ?? ',';
  const decimal = parts.find(p => p.type === 'decimal')?.value ?? '.';
  const intIdx = parts.findIndex(p => p.type === 'integer');
  const minusPrefix = intIdx !== -1 ? parts.slice(0, intIdx).map(p => p.value).join('') : '-';
  let lastNumberPartIdx = -1;
  for (let i = parts.length - 1; i >= 0; i--) {
    if (parts[i]?.type === 'fraction' || parts[i]?.type === 'integer') {
      lastNumberPartIdx = i;
      break;
    }
  }
  const minusSuffix =
    lastNumberPartIdx !== -1
      ? parts.slice(lastNumberPartIdx + 1).map(p => p.value).join('')
      : '';

  const digits = Array.from({ length: 10 }, (_, i) => nf.format(i));

  const isNegative = value.startsWith('-');
  const unsigned = isNegative ? value.slice(1) : value;
  const [rawInt = '', rawFrac] = unsigned.split('.');

  const groupedInt = rawInt.replace(/\B(?=(\d{3})+(?!\d))/g, group);
  const formattedInt = groupedInt.replace(/\d/g, d => digits[Number(d)] ?? d);

  const frac = (rawFrac ?? '').slice(0, 6).replace(/0+$/, '');
  let formattedFrac = '';
  if (frac.length > 0) {
    formattedFrac = decimal + frac.replace(/\d/g, d => digits[Number(d)] ?? d);
  }

  const signPrefix = isNegative ? minusPrefix : '';
  const signSuffix = isNegative ? minusSuffix : '';

  return `${signPrefix}${formattedInt}${formattedFrac}${signSuffix}`;
}

/**
 * Pure locale-aware money formatter with explicit currency code, thousands separators,
 * 0 or 2 fraction digits (e.g. `EGP 56,425`, `EGP 56,425.50`), and Arabic-Indic digits for 'ar'.
 */
export function formatCurrencyAmount(
  value: MoneyLike | null | undefined,
  locale = 'en',
): string {
  if (!value || value.amount === null || value.amount === undefined || !value.currency) {
    return '—';
  }

  const numAmount = typeof value.amount === 'number' ? value.amount : parseFloat(value.amount);
  if (isNaN(numAmount)) {
    const symbol = isArabicLocale(locale) ? currencySymbol(value.currency, locale) : value.currency;
    return `— ${symbol}`;
  }

  const isZero = Math.abs(numAmount) < 0.005;
  const normalizedAmount = isZero ? 0 : numAmount;
  const rounded = isZero
    ? 0
    : (Math.sign(normalizedAmount) * Math.round(Math.abs(normalizedAmount) * 100)) / 100;
  const fractionDigits = Number.isInteger(rounded) ? 0 : 2;

  const formattedNumber = formatLocaleNumber(normalizedAmount, locale, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });

  if (isArabicLocale(locale)) {
    const symbol = currencySymbol(value.currency, locale);
    return `${formattedNumber} ${symbol}`;
  }

  return `${value.currency} ${formattedNumber}`;
}

/**
 * Service for locale-aware monetary, quantity, and date formatting.
 *
 * Constitution Principle VII & T069:
 * Every monetary amount must render with an explicit currency.
 * There is no such thing as a bare number for money in ProcurePilot.
 */
@Injectable({ providedIn: 'root' })
export class FormatService {
  private readonly translate = inject(TranslateService, { optional: true });

  private resolveLocale(localeOverride?: string): string {
    if (localeOverride) {
      return localeOverride;
    }
    const active = this.translate?.getCurrentLang() || this.translate?.getFallbackLang();
    return active || 'en';
  }

  currencySymbol(currency: string, localeOverride?: string): string {
    return currencySymbol(currency, this.resolveLocale(localeOverride));
  }

  /**
   * Formats a monetary value with explicit currency and locale sensitivity.
   *
   * @param value Money object containing decimal amount and ISO 4217 currency.
   * @param localeOverride Optional locale override (e.g. 'en' or 'ar').
   */
  formatMoney(
    value: MoneyLike | null | undefined,
    localeOverride?: string,
  ): string {
    if (!value || value.amount === null || value.amount === undefined || !value.currency) {
      return '—';
    }

    const numAmount = typeof value.amount === 'number' ? value.amount : parseFloat(value.amount);
    if (isNaN(numAmount)) {
      return `— ${value.currency}`;
    }

    const isZero = Math.abs(numAmount) < 0.005;
    const normalizedAmount = isZero ? 0 : numAmount;

    const locale = this.resolveLocale(localeOverride);

    try {
      return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: value.currency,
        currencyDisplay: 'symbol',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
        ...(isArabicLocale(locale) ? { numberingSystem: 'arab' } : {}),
      }).format(normalizedAmount);
    } catch {
      const formattedNumber = normalizedAmount.toLocaleString(locale, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
      return `${formattedNumber} ${value.currency}`;
    }
  }

  /**
   * Formats a monetary value with explicit currency code, thousands separators,
   * 0 or 2 fraction digits (`EGP 56,425`; `EGP 56,425.50`), and Arabic-Indic digits for `ar`.
   */
  formatCurrencyAmount(
    value: MoneyLike | null | undefined,
    localeOverride?: string,
  ): string {
    return formatCurrencyAmount(value, this.resolveLocale(localeOverride));
  }

  /**
   * Formats a quantity with thousands separators, up to 2 decimals trimmed (`15.000000` -> `15`),
   * and Arabic-Indic digits when locale is `ar`.
   */
  formatQuantity(
    value: number | string | null | undefined,
    localeOverride?: string,
  ): string {
    return formatLocaleNumber(value, this.resolveLocale(localeOverride), {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
  }

  /**
   * Formats a quantity with exact precision up to 6 fraction digits trimmed (`0.000001` -> `0.000001`, `50.000000` -> `50`),
   * preserving precision for numeric(18,6) database values, with Arabic-Indic digits for `ar`.
   */
  formatExactQuantity(
    value: number | string | null | undefined,
    localeOverride?: string,
  ): string {
    return formatExactQuantity(value, this.resolveLocale(localeOverride));
  }

  /**
   * Formats a date string or Date object with locale sensitivity.
   */
  formatDate(
    date: string | Date | number | null | undefined,
    options: Intl.DateTimeFormatOptions = { dateStyle: 'medium' },
    localeOverride?: string,
  ): string {
    if (!date) return '—';

    const d = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date;
    if (isNaN(d.getTime())) return '—';

    const locale = this.resolveLocale(localeOverride);
    const resolvedOptions: Intl.DateTimeFormatOptions = {
      ...(isArabicLocale(locale) ? { numberingSystem: 'arab' } : {}),
      ...options,
    };
    return new Intl.DateTimeFormat(locale, resolvedOptions).format(d);
  }

  /**
   * Formats a numeric value with locale decimal separators (defaults to 0-2 fraction digits
   * and Arabic-Indic digits for 'ar').
   */
  formatNumber(
    value: number | string | null | undefined,
    options?: Intl.NumberFormatOptions,
    localeOverride?: string,
  ): string {
    return formatLocaleNumber(value, this.resolveLocale(localeOverride), options);
  }
}
