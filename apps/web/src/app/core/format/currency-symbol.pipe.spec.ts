import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import { CurrencySymbolPipe } from './currency-symbol.pipe';
import { FormatService } from './format.service';

describe('CurrencySymbolPipe', () => {
  let pipe: CurrencySymbolPipe;
  let translate: TranslateService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideTranslateService({ fallbackLang: 'en' }),
        FormatService,
        CurrencySymbolPipe,
      ],
    });
    pipe = TestBed.inject(CurrencySymbolPipe);
    translate = TestBed.inject(TranslateService);
  });

  it('transforms ISO currency code to symbol in Arabic locale', () => {
    translate.use('ar');
    expect(pipe.transform('EGP')).toBe('ج.م');
    expect(pipe.transform('SAR')).toBe('ر.س');
    expect(pipe.transform('EUR')).toBe('€');
  });

  it('retains ISO currency code in English locale', () => {
    translate.use('en');
    expect(pipe.transform('EGP')).toBe('EGP');
    expect(pipe.transform('SAR')).toBe('SAR');
  });

  it('handles null and empty input gracefully', () => {
    expect(pipe.transform(null)).toBe('');
    expect(pipe.transform(undefined)).toBe('');
    expect(pipe.transform('')).toBe('');
  });
});
