import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import {
  FormatService,
  currencySymbol,
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
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideTranslateService({ fallbackLang: 'en' }),
        FormatService,
      ],
    });
    service = TestBed.inject(FormatService);
    translate = TestBed.inject(TranslateService);
  });

  describe('currencySymbol', () => {
    it('returns Arabic currency symbols for Arabic locales and ISO code for others (PPS-84)', () => {
      expect(currencySymbol('EGP', 'ar')).toBe('ج.م');
      expect(currencySymbol('SAR', 'ar')).toBe('ر.س');
      expect(currencySymbol('EUR', 'ar')).toBe('€');
      expect(currencySymbol('USD', 'ar')).toBe('US$');
      expect(currencySymbol('EGP', 'en')).toBe('EGP');
      expect(currencySymbol('SAR', 'en')).toBe('SAR');
      expect(currencySymbol('XYZ', 'ar')).toBe('XYZ');
    });

    it('resolves active locale through FormatService.currencySymbol', () => {
      translate.use('ar');
      expect(service.currencySymbol('EGP')).toBe('ج.م');
      translate.use('en');
      expect(service.currencySymbol('EGP')).toBe('EGP');
    });
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

    it('displays negative zero and sub-cent negative as zero with no minus sign', () => {
      const zeroExpected = service.formatMoney({ amount: '0', currency: 'SAR' }, 'en');
      const negZero = service.formatMoney({ amount: '-0.0000', currency: 'SAR' }, 'en');
      const subCent = service.formatMoney({ amount: '-0.0020', currency: 'SAR' }, 'en');
      const justUnderHalfCent = service.formatMoney({ amount: '-0.0049', currency: 'SAR' }, 'en');
      expect(negZero).not.toContain('-');
      expect(negZero).toBe(zeroExpected);
      expect(subCent).not.toContain('-');
      expect(subCent).toBe(zeroExpected);
      expect(justUnderHalfCent).not.toContain('-');
      expect(justUnderHalfCent).toBe(zeroExpected);

      const halfCentNegative = service.formatMoney({ amount: '-0.0050', currency: 'SAR' }, 'en');
      expect(halfCentNegative).toBe(
        service.formatMoney({ amount: '-0.01', currency: 'SAR' }, 'en'),
      );
      expect(halfCentNegative).toContain('-');
      expect(halfCentNegative).toContain('0.01');
    });
  });

  describe('formatCurrencyAmount (0 or 2 fraction digits, locale-aware)', () => {
    it('formats money with thousands separators and 0 or 2 fraction digits in en', () => {
      translate.use('en');
      expect(service.formatCurrencyAmount({ amount: '56425.0000', currency: 'EGP' })).toBe(
        'EGP 56,425',
      );
      expect(service.formatCurrencyAmount({ amount: '56425.5000', currency: 'EGP' })).toBe(
        'EGP 56,425.50',
      );
      expect(service.formatCurrencyAmount({ amount: '56425.5500', currency: 'EGP' })).toBe(
        'EGP 56,425.55',
      );
      expect(formatCurrencyAmount({ amount: '1289.5000', currency: 'EUR' }, 'en')).toBe(
        'EUR 1,289.50',
      );
      expect(formatCurrencyAmount({ amount: '500.0000', currency: 'GBP' }, 'en')).toBe('GBP 500');
    });

    it('formats negative zero and sub-cent negative as zero without minus sign, and half-cent as negative one-cent', () => {
      expect(service.formatCurrencyAmount({ amount: '-0.0000', currency: 'SAR' }, 'en')).toBe(
        'SAR 0',
      );
      expect(service.formatCurrencyAmount({ amount: '-0.0020', currency: 'SAR' }, 'en')).toBe(
        'SAR 0',
      );
      expect(service.formatCurrencyAmount({ amount: '-0.0049', currency: 'SAR' }, 'en')).toBe(
        'SAR 0',
      );
      expect(service.formatCurrencyAmount({ amount: '-0.0050', currency: 'SAR' }, 'en')).toBe(
        'SAR -0.01',
      );
      expect(formatCurrencyAmount({ amount: '-0.0000', currency: 'SAR' }, 'en')).toBe('SAR 0');
      expect(formatCurrencyAmount({ amount: '-0.0020', currency: 'SAR' }, 'en')).toBe('SAR 0');
      expect(formatCurrencyAmount({ amount: '-0.0049', currency: 'SAR' }, 'en')).toBe('SAR 0');
      expect(formatCurrencyAmount({ amount: '-0.0050', currency: 'SAR' }, 'en')).toBe('SAR -0.01');
    });

    it('formats money with Arabic currency symbol after the number when active ngx-translate language is ar (PPS-84)', () => {
      translate.use('ar');
      const intFormatted = service.formatCurrencyAmount({ amount: '56425.0000', currency: 'EGP' });
      expect(intFormatted).toBe('٥٦٬٤٢٥ ج.م');

      const decFormatted = service.formatCurrencyAmount({ amount: '56425.5000', currency: 'EGP' });
      expect(decFormatted).toBe('٥٦٬٤٢٥٫٥٠ ج.م');
    });

    it('formats pure formatCurrencyAmount with Arabic currency symbol after the number (PPS-84)', () => {
      expect(formatCurrencyAmount({ amount: '56425', currency: 'EGP' }, 'ar')).toBe('٥٦٬٤٢٥ ج.م');
      expect(formatCurrencyAmount({ amount: '56425.5', currency: 'EGP' }, 'ar')).toBe('٥٦٬٤٢٥٫٥٠ ج.م');
      expect(formatCurrencyAmount({ amount: '190', currency: 'SAR' }, 'ar')).toBe('١٩٠ ر.س');
      expect(formatCurrencyAmount({ amount: '13', currency: 'EUR' }, 'ar')).toBe('١٣ €');
      expect(formatCurrencyAmount({ amount: '0', currency: 'EGP' }, 'ar')).toBe('٠ ج.م');
      expect(formatCurrencyAmount({ amount: '-0.0000', currency: 'EGP' }, 'ar')).toBe('٠ ج.م');
      expect(formatCurrencyAmount({ amount: '56425', currency: 'EGP' }, 'en')).toBe('EGP 56,425');

      const unknownCurr = formatCurrencyAmount({ amount: '100', currency: 'XYZ' }, 'ar');
      expect(unknownCurr).toContain('XYZ');
      expect(unknownCurr).toContain('١٠٠');
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
      expect(service.formatExactQuantity('999999999999.999999')).toBe('999,999,999,999.999999');
      expect(service.formatExactQuantity('1234567.100000')).toBe('1,234,567.1');
      expect(service.formatExactQuantity('-12.500000')).toBe('-12.5');
      expect(formatExactQuantity('0.000001', 'en')).toBe('0.000001');
      expect(formatExactQuantity('1.234567', 'en')).toBe('1.234567');
      expect(formatExactQuantity('50.000000', 'en')).toBe('50');
      expect(formatExactQuantity('999999999999.999999', 'en')).toBe('999,999,999,999.999999');
      expect(formatExactQuantity('1234567.100000', 'en')).toBe('1,234,567.1');
      expect(formatExactQuantity('-12.500000', 'en')).toBe('-12.5');
    });

    it('renders Arabic-Indic digits for exact 6-decimal quantities when locale is ar', () => {
      translate.use('ar');
      expect(service.formatExactQuantity('0.000001')).toBe('٠٫٠٠٠٠٠١');
      expect(service.formatExactQuantity('1.234567')).toBe('١٫٢٣٤٥٦٧');
      expect(service.formatExactQuantity('50.000000')).toBe('٥٠');
      expect(service.formatExactQuantity('999999999999.999999')).toBe('٩٩٩٬٩٩٩٬٩٩٩٬٩٩٩٫٩٩٩٩٩٩');
      expect(service.formatExactQuantity('1234567.100000')).toBe('١٬٢٣٤٬٥٦٧٫١');
      expect(service.formatExactQuantity('-12.500000')).toBe('؜-١٢٫٥');
      expect(formatExactQuantity('0.000001', 'ar')).toBe('٠٫٠٠٠٠٠١');
      expect(formatExactQuantity('1.234567', 'ar')).toBe('١٫٢٣٤٥٦٧');
      expect(formatExactQuantity('50.000000', 'ar')).toBe('٥٠');
      expect(formatExactQuantity('999999999999.999999', 'ar')).toBe('٩٩٩٬٩٩٩٬٩٩٩٬٩٩٩٫٩٩٩٩٩٩');
      expect(formatExactQuantity('1234567.100000', 'ar')).toBe('١٬٢٣٤٬٥٦٧٫١');
      expect(formatExactQuantity('-12.500000', 'ar')).toBe('؜-١٢٫٥');
    });

    it('retains default 2-decimal truncation for formatQuantity', () => {
      translate.use('en');
      expect(service.formatQuantity('0.000001')).toBe('0');
      expect(service.formatQuantity('1.234567')).toBe('1.23');
      expect(service.formatQuantity('50.000000')).toBe('50');
    });
  });

  describe('formatDate', () => {
    it('should format date for locale with Arabic-Indic digits for ar and ASCII digits for en', () => {
      const d = new Date('2026-08-20T10:00:00Z');
      const enResult = service.formatDate(d, { dateStyle: 'medium' }, 'en');
      expect(enResult).toContain('2026');
      expect(/[0-9]/.test(enResult)).toBeTrue();

      const arResult = service.formatDate(d, { dateStyle: 'medium' }, 'ar');
      expect(arResult.length).toBeGreaterThan(0);
      expect(arResult).toContain('٢٠٢٦');
      expect(/[0-9]/.test(arResult)).toBeFalse();

      const overrideResult = service.formatDate(
        d,
        { dateStyle: 'medium', numberingSystem: 'latn' },
        'ar',
      );
      expect(overrideResult).toContain('2026');
      expect(/[0-9]/.test(overrideResult)).toBeTrue();
    });

    it('should return placeholder for null date', () => {
      expect(service.formatDate(null)).toBe('—');
    });
  });
});
