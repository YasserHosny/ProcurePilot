import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';

import { FormatService } from './format.service';

describe('FormatService (T069)', () => {
  let service: FormatService;

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
