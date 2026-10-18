import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import {
  FormatService,
  formatCurrencyAmount,
  formatExactQuantity,
  formatLocaleNumber,
} from './format.service';

describe('FormatService (T069)', () => {
  let service: FormatService;
  let translate: TranslateService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTranslateService({ defaultLanguage: 'en' }),
        FormatService,
      ],
    });
    service = TestBed.inject(FormatService);
    translate = TestBed.inject(TranslateService);
  });

  describe('formatMoney', () => {
    it('should format money with explicit currency in English locale', () => {
      const result = service.formatMoney({ amount: '1234.50', currency: 'SAR' }, 'en');
      expect(result).toContain('SAR');
      expect(result).toContain('1,234.50');
    });

    it('should format money with explicit currency in Arabic locale', () => {
      const result = service.formatMoney({ amount: '1234.50', currency: 'SAR' }, 'ar');
      expect(result.length).toBeGreaterThan(0);
      const hasCurrency = result.includes('SAR') || result.includes('ر.س') || result.includes('ر.س.');
      expect(hasCurrency).toBeTrue();
    });

    it('should return placeholder for null or missing amount', () => {
      expect(service.formatMoney(null)).toBe('—');
      expect(service.formatMoney(undefined)).toBe('—');
    });

    it('should always include currency even if amount is NaN', () => {
      const result = service.formatMoney({ amount: 'invalid', currency: 'USD' });
      expect(result).toContain('USD');
    });
  });

  describe('formatCurrencyAmount (0–2 fraction digits, locale-aware)', () => {
    it('formats money with thousands separators and 0–2 fraction digits in en', () => {
      translate.use('en');
      expect(service.formatCurrencyAmount({ amount: '56425.0000', currency: 'EGP' })).toBe(
        'EGP 56,425',
      );
      expect(service.formatCurrencyAmount({ amount: '56425.5000', currency: 'EGP' })).toBe(
        'EGP 56,425.5',
      );
      expect(service.formatCurrencyAmount({ amount: '56425.5500', currency: 'EGP' })).toBe(
        'EGP 56,425.55',
      );
      expect(formatCurrencyAmount({ amount: '500.0000', currency: 'GBP' }, 'en')).toBe('GBP 500');
    });

    it('formats money with Arabic-Indic digits when active ngx-translate language is ar', () => {
      translate.use('ar');
      const intFormatted = service.formatCurrencyAmount({ amount: '56425.0000', currency: 'EGP' });
      expect(intFormatted).toContain('EGP');
      expect(intFormatted).toContain('٥٦');
      expect(intFormatted).toContain('٤٢٥');
      expect(intFormatted).not.toContain('56425');

      const decFormatted = service.formatCurrencyAmount({ amount: '56425.5000', currency: 'EGP' });
      expect(decFormatted).toContain('EGP');
      expect(decFormatted).toContain('٥');
      expect(decFormatted).not.toContain('000');
    });

    it('returns placeholder for null or missing money values', () => {
      expect(service.formatCurrencyAmount(null)).toBe('—');
      expect(service.formatCurrencyAmount(undefined)).toBe('—');
    });
  });

  describe('formatQuantity / formatNumber (trimmed up to 2 decimals, locale-aware)', () => {
    it('trims trailing zeros up to 2 decimals with thousands separators in en', () => {
      translate.use('en');
      expect(service.formatQuantity('15.000000')).toBe('15');
      expect(service.formatQuantity('15.500000')).toBe('15.5');
      expect(service.formatQuantity('15.250000')).toBe('15.25');
      expect(service.formatQuantity('1500.000000')).toBe('1,500');
      expect(formatLocaleNumber('15.000000', 'en')).toBe('15');
    });

    it('renders Arabic-Indic digits with trimmed decimals when locale is ar', () => {
      translate.use('ar');
      const qty15 = service.formatQuantity('15.000000');
      expect(qty15).toBe('١٥');

      const qtyDec = service.formatQuantity('15.500000');
      expect(qtyDec).toContain('١٥');
      expect(qtyDec).toContain('٥');
      expect(qtyDec).not.toContain('0');
    });
  });

  describe('formatExactQuantity (up to 6 decimals, numeric(18,6) precision)', () => {
    it('formats 6-decimal quantities trimming trailing zeroes in en', () => {
      translate.use('en');
      expect(service.formatExactQuantity('0.000001')).toBe('0.000001');
      expect(service.formatExactQuantity('1.234567')).toBe('1.234567');
      expect(service.formatExactQuantity('50.000000')).toBe('50');
      expect(formatExactQuantity('0.000001', 'en')).toBe('0.000001');
      expect(formatExactQuantity('1.234567', 'en')).toBe('1.234567');
      expect(formatExactQuantity('50.000000', 'en')).toBe('50');
    });

    it('renders Arabic-Indic digits for exact 6-decimal quantities when locale is ar', () => {
      translate.use('ar');
      expect(service.formatExactQuantity('0.000001')).toBe('٠٫٠٠٠٠٠١');
      expect(service.formatExactQuantity('1.234567')).toBe('١٫٢٣٤٥٦٧');
      expect(service.formatExactQuantity('50.000000')).toBe('٥٠');
      expect(formatExactQuantity('0.000001', 'ar')).toBe('٠٫٠٠٠٠٠١');
      expect(formatExactQuantity('1.234567', 'ar')).toBe('١٫٢٣٤٥٦٧');
      expect(formatExactQuantity('50.000000', 'ar')).toBe('٥٠');
    });

    it('retains default 2-decimal truncation for formatQuantity', () => {
      translate.use('en');
      expect(service.formatQuantity('0.000001')).toBe('0');
      expect(service.formatQuantity('1.234567')).toBe('1.23');
      expect(service.formatQuantity('50.000000')).toBe('50');
    });
  });

  describe('formatDate', () => {
    it('should format date for locale', () => {
      const d = new Date('2026-08-20T10:00:00Z');
      const enResult = service.formatDate(d, { dateStyle: 'medium' }, 'en');
      expect(enResult).toContain('2026');

      const arResult = service.formatDate(d, { dateStyle: 'medium' }, 'ar');
      expect(arResult.length).toBeGreaterThan(0);
    });

    it('should return placeholder for null date', () => {
      expect(service.formatDate(null)).toBe('—');
    });
  });
});
