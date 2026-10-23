import { provideHttpClient, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import { FormatService } from './format.service';
import {
  FormatExtractionPipe,
  formatExtractionValue,
  isDateField,
  isExtractionJsonFallback,
  isIsoDateString,
  isMoneyLike,
} from './extraction-value.pipe';

describe('FormatExtractionPipe and extraction formatting helpers', () => {
  let pipe: FormatExtractionPipe;
  let service: FormatService;
  let translate: TranslateService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withXhr()),
        provideHttpClientTesting(),
        provideTranslateService({ defaultLanguage: 'en' }),
        FormatService,
        FormatExtractionPipe,
      ],
    });
    service = TestBed.inject(FormatService);
    pipe = TestBed.inject(FormatExtractionPipe);
    translate = TestBed.inject(TranslateService);
    translate.use('en');
  });

  describe('isMoneyLike', () => {
    it('returns true for valid money-like objects', () => {
      expect(isMoneyLike({ amount: '24220.00', currency: 'EGP' })).toBeTrue();
      expect(isMoneyLike({ amount: 150.5, currency: 'SAR' })).toBeTrue();
    });

    it('returns false for non-money values', () => {
      expect(isMoneyLike(null)).toBeFalse();
      expect(isMoneyLike(undefined)).toBeFalse();
      expect(isMoneyLike('24220.00')).toBeFalse();
      expect(isMoneyLike({ amount: '24220.00' })).toBeFalse();
      expect(isMoneyLike({ currency: 'EGP' })).toBeFalse();
      expect(isMoneyLike({ amount: '', currency: 'EGP' })).toBeFalse();
      expect(isMoneyLike({ amount: NaN, currency: 'EGP' })).toBeFalse();
      expect(isMoneyLike([1, 2, 3])).toBeFalse();
    });
  });

  describe('isDateField and isIsoDateString', () => {
    it('detects date field names', () => {
      expect(isDateField('issue_date')).toBeTrue();
      expect(isDateField('expiry_date')).toBeTrue();
      expect(isDateField('expected_delivery_date')).toBeTrue();
      expect(isDateField('supplier_name')).toBeFalse();
      expect(isDateField('notes')).toBeFalse();
      expect(isDateField(null)).toBeFalse();
      expect(isDateField(undefined)).toBeFalse();
    });

    it('detects ISO date strings', () => {
      expect(isIsoDateString('2026-08-20')).toBeTrue();
      expect(isIsoDateString('2026-08-20T12:00:00Z')).toBeTrue();
      expect(isIsoDateString('2026-08-20T12:00:00+02:00')).toBeTrue();
      expect(isIsoDateString('not-a-date')).toBeFalse();
      expect(isIsoDateString('Order placed on 2026-08-20')).toBeFalse();
    });
  });

  describe('isExtractionJsonFallback', () => {
    it('returns true only for unknown objects and arrays', () => {
      expect(isExtractionJsonFallback({ unknown_prop: 'val' })).toBeTrue();
      expect(isExtractionJsonFallback(['a', 'b'])).toBeTrue();

      expect(isExtractionJsonFallback({ amount: '100', currency: 'USD' })).toBeFalse();
      expect(isExtractionJsonFallback('plain string')).toBeFalse();
      expect(isExtractionJsonFallback('2026-08-20')).toBeFalse();
      expect(isExtractionJsonFallback(1234)).toBeFalse();
      expect(isExtractionJsonFallback(true)).toBeFalse();
      expect(isExtractionJsonFallback(null)).toBeFalse();
      expect(isExtractionJsonFallback(undefined)).toBeFalse();
    });
  });

  describe('formatExtractionValue and pipe transform', () => {
    it('returns empty string for null and undefined', () => {
      expect(pipe.transform(null)).toBe('');
      expect(pipe.transform(undefined)).toBe('');
      expect(formatExtractionValue(null)).toBe('');
      expect(formatExtractionValue(undefined)).toBe('');
    });

    it('formats money-shaped objects through FormatService.formatMoney', () => {
      const moneyVal = { amount: '24220.00', currency: 'EGP' };
      const formattedEn = pipe.transform(moneyVal);
      expect(formattedEn).toBe(service.formatMoney(moneyVal, 'en'));
      expect(formattedEn).not.toContain('"amount"');
      expect(formattedEn).not.toContain('{');

      translate.use('ar');
      const formattedAr = pipe.transform(moneyVal);
      expect(formattedAr).toBe(service.formatMoney(moneyVal, 'ar'));
      expect(formattedAr).toContain('٢٤');
    });

    it('formats date field ISO strings through FormatService.formatDate with local date interpretation', () => {
      const formatted = pipe.transform('2026-08-20', 'issue_date');
      expect(formatted).toBe(service.formatDate(new Date(2026, 7, 20)));
      expect(formatted).not.toBe('2026-08-20');
    });

    it('formats plain ISO date strings when fieldName is not provided', () => {
      const formatted = pipe.transform('2026-08-20');
      expect(formatted).toBe(service.formatDate(new Date(2026, 7, 20)));
    });

    it('asserts pure date-only string output in en contains "20" and not "19"', () => {
      translate.use('en');
      const formatted = pipe.transform('2026-08-20', 'issue_date');
      expect(formatted).toContain('20');
      expect(formatted).not.toContain('19');
    });

    it('formats datetime strings with offset on issue_date from literal YYYY-MM-DD components', () => {
      const formatted = pipe.transform('2026-08-20T00:30:00+02:00', 'issue_date');
      expect(formatted).toBe(service.formatDate(new Date(2026, 7, 20)));
      expect(formatted).toContain('20');
    });

    it('returns invalid calendar date 2026-02-31 on issue_date as raw string', () => {
      expect(pipe.transform('2026-02-31', 'issue_date')).toBe('2026-02-31');
    });

    it('returns invalid calendar date 2026-13-01 on expiry_date as raw string', () => {
      expect(pipe.transform('2026-13-01', 'expiry_date')).toBe('2026-13-01');
    });

    it('leaves ISO date strings unformatted when fieldName is not a date field', () => {
      const formatted = pipe.transform('2026-08-20', 'supplier_name');
      expect(formatted).toBe('2026-08-20');
    });

    it('leaves plain strings untouched', () => {
      expect(pipe.transform('Acme Supplies Ltd', 'supplier_name')).toBe('Acme Supplies Ltd');
      expect(pipe.transform('شركة الأمانة للتجارة')).toBe('شركة الأمانة للتجارة');
    });

    it('formats numeric values with locale formatting', () => {
      translate.use('en');
      expect(pipe.transform(1234.5)).toBe(service.formatNumber(1234.5, undefined, 'en'));

      translate.use('ar');
      expect(pipe.transform(1234.5)).toBe(service.formatNumber(1234.5, undefined, 'ar'));
    });

    it('converts boolean values to string', () => {
      expect(pipe.transform(true)).toBe('true');
      expect(pipe.transform(false)).toBe('false');
    });

    it('serializes unknown objects to JSON as fallback', () => {
      const obj = { nested: { count: 2 } };
      expect(pipe.transform(obj)).toBe(JSON.stringify(obj));
    });
  });
});
