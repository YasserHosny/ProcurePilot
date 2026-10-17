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
 * Pure locale-aware money formatter with explicit currency code, thousands separators,
 * 0-2 fraction digits (e.g. `EGP 56,425`, `EGP 56,425.5`), and Arabic-Indic digits for 'ar'.
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
    return `— ${value.currency}`;
  }

  const formattedNumber = formatLocaleNumber(numAmount, locale, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
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
    const active = this.translate?.currentLang || this.translate?.getDefaultLang();
    return active || 'en';
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

    const locale = this.resolveLocale(localeOverride);

    try {
      return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: value.currency,
        currencyDisplay: 'symbol',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
        ...(isArabicLocale(locale) ? { numberingSystem: 'arab' } : {}),
      }).format(numAmount);
    } catch {
      const formattedNumber = numAmount.toLocaleString(locale, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
      return `${formattedNumber} ${value.currency}`;
    }
  }

  /**
   * Formats a monetary value with explicit currency code, thousands separators,
   * 0-2 fraction digits (`EGP 56,425`; `EGP 56,425.5`), and Arabic-Indic digits for `ar`.
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
    return new Intl.DateTimeFormat(locale, options).format(d);
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
