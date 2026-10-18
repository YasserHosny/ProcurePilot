import { Pipe, PipeTransform, inject } from '@angular/core';

import { FormatService, formatCurrencyAmount, formatLocaleNumber } from './format.service';

/**
 * Returns true if the value is a money-shaped object having an amount
 * (string or number) and a non-empty string currency code.
 */
export function isMoneyLike(
  value: unknown,
): value is { amount: string | number; currency: string } {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  const hasAmount =
    (typeof candidate['amount'] === 'string' && candidate['amount'].trim().length > 0) ||
    (typeof candidate['amount'] === 'number' && !Number.isNaN(candidate['amount']));
  const hasCurrency =
    typeof candidate['currency'] === 'string' && candidate['currency'].trim().length > 0;
  return hasAmount && hasCurrency;
}

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;
const PURE_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * Returns true if the field name represents a known date extraction field.
 */
export function isDateField(fieldName?: string | null): boolean {
  if (!fieldName) return false;
  const normalized = fieldName.trim().toLowerCase();
  return (
    normalized === 'issue_date' ||
    normalized === 'expiry_date' ||
    normalized.endsWith('_date')
  );
}

/**
 * Returns true if the string is a valid ISO date or datetime string.
 */
export function isIsoDateString(value: string): boolean {
  return ISO_DATE_PATTERN.test(value.trim());
}

/**
 * Returns true only when an extracted value is an unrecognized object or array
 * that must fall back to JSON serialization and be displayed with monospace styling.
 */
export function isExtractionJsonFallback(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value !== 'object') return false;
  if (isMoneyLike(value)) return false;
  return true;
}

/**
 * Pure helper that turns an extracted field value into localized display text:
 * - Money-shaped objects ({ amount, currency }) -> FormatService.formatMoney
 * - ISO date strings on date fields (or plain ISO dates) -> FormatService.formatDate
 * - Numbers -> FormatService.formatNumber
 * - Plain strings -> untouched
 * - Unknown objects/arrays -> JSON.stringify fallback
 * - null/undefined -> ''
 */
export function formatExtractionValue(
  value: unknown,
  fieldName?: string | null,
  formatService?: FormatService | null,
  localeOverride?: string,
): string {
  if (value === null || value === undefined) {
    return '';
  }

  if (isMoneyLike(value)) {
    return formatService
      ? formatService.formatMoney(value, localeOverride)
      : formatCurrencyAmount(value, localeOverride);
  }

  if (typeof value === 'string') {
    if ((isDateField(fieldName) || !fieldName) && isIsoDateString(value)) {
      if (!formatService) return value;
      const trimmed = value.trim();
      const pureDateMatch = PURE_DATE_PATTERN.exec(trimmed);
      const dateToFormat: Date | string = pureDateMatch
        ? new Date(
            Number(pureDateMatch[1]),
            Number(pureDateMatch[2]) - 1,
            Number(pureDateMatch[3]),
          )
        : trimmed;
      return formatService.formatDate(dateToFormat, { dateStyle: 'medium' }, localeOverride);
    }
    return value;
  }

  if (typeof value === 'number') {
    return formatService
      ? formatService.formatNumber(value, undefined, localeOverride)
      : formatLocaleNumber(value, localeOverride);
  }

  if (typeof value === 'boolean') {
    return String(value);
  }

  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }

  return String(value);
}

/**
 * Standalone pipe to format extracted field values with locale awareness.
 *
 * Example: {{ field.extraction.extracted_value | formatExtraction: field.fieldName }}
 */
@Pipe({
  name: 'formatExtraction',
  standalone: true,
  // Impure so dynamic locale switches (e.g. TranslateService.use) re-render immediately.
  pure: false,
})
export class FormatExtractionPipe implements PipeTransform {
  private readonly formatService = inject(FormatService);

  transform(
    value: unknown,
    fieldName?: string | null,
    localeOverride?: string,
  ): string {
    return formatExtractionValue(value, fieldName, this.formatService, localeOverride);
  }
}
