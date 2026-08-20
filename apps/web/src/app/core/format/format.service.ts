import { Injectable, inject } from '@angular/core';

import type { Money } from '../api/models';
import { I18nService } from '../i18n/i18n.service';

/**
 * Service for locale-aware monetary and date formatting.
 *
 * Constitution Principle VII & T069:
 * Every monetary amount must render with an explicit currency.
 * There is no such thing as a bare number for money in ProcurePilot.
 */
@Injectable({ providedIn: 'root' })
export class FormatService {
  private readonly i18n = inject(I18nService);

  /**
   * Formats a monetary value with explicit currency and locale sensitivity.
   *
   * @param value Money object containing decimal amount and ISO 4217 currency.
   * @param localeOverride Optional locale override (e.g. 'en' or 'ar').
   */
  formatMoney(
    value: Money | { amount: string | number; currency: string } | null | undefined,
    localeOverride?: string,
  ): string {
    if (!value || value.amount === null || value.amount === undefined || !value.currency) {
      return '—';
    }

    const numAmount = typeof value.amount === 'number' ? value.amount : parseFloat(value.amount);
    if (isNaN(numAmount)) {
      return `— ${value.currency}`;
    }

    const locale = localeOverride || this.i18n.currentLocale() || 'en';

    try {
      return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: value.currency,
        currencyDisplay: 'symbol',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(numAmount);
    } catch {
      // Fallback if currency code or locale is unsupported by browser Intl
      const formattedNumber = numAmount.toLocaleString(locale, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
      return `${formattedNumber} ${value.currency}`;
    }
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

    const locale = localeOverride || this.i18n.currentLocale() || 'en';
    return new Intl.DateTimeFormat(locale, options).format(d);
  }

  /**
   * Formats a numeric value with locale decimal separators.
   */
  formatNumber(
    value: number | string | null | undefined,
    options?: Intl.NumberFormatOptions,
    localeOverride?: string,
  ): string {
    if (value === null || value === undefined) return '—';

    const num = typeof value === 'number' ? value : parseFloat(value);
    if (isNaN(num)) return '—';

    const locale = localeOverride || this.i18n.currentLocale() || 'en';
    return new Intl.NumberFormat(locale, options).format(num);
  }
}
